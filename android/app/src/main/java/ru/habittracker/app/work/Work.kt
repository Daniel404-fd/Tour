package ru.habittracker.app.work

import android.Manifest
import android.app.AlarmManager
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import ru.habittracker.app.App
import ru.habittracker.app.MainActivity
import ru.habittracker.app.R
import ru.habittracker.app.data.Cal
import java.time.LocalDateTime
import java.time.ZoneId
import java.util.concurrent.TimeUnit

/** Синхронизация в фоне раз в час (Android сам выбирает момент, когда есть интернет). */
class SyncWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val app = applicationContext as App
        return if (!app.sync.enabled || app.sync.syncNow()) Result.success() else Result.retry()
    }

    companion object {
        fun schedule(ctx: Context) {
            val req = PeriodicWorkRequestBuilder<SyncWorker>(1, TimeUnit.HOURS)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(ctx).enqueueUniquePeriodicWork("sync", ExistingPeriodicWorkPolicy.KEEP, req)
        }
    }
}

/** Напоминания календаря: будильники Android на ближайшие 2 дня, пересчитываются при изменениях. */
object Reminders {
    const val CHANNEL = "reminders"
    private const val MAX = 40

    fun schedule(ctx: Context) {
        val app = ctx.applicationContext as App
        val am = ctx.getSystemService(AlarmManager::class.java)
        // снять прежние
        for (i in 0 until MAX) {
            PendingIntent.getBroadcast(ctx, i, Intent(ctx, ReminderReceiver::class.java),
                PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE)?.let { am.cancel(it); it.cancel() }
        }
        val visible = app.repo.calendars().filter { it.visible }.map { it.id }.toSet()
        val events = app.repo.events().filter { it.reminder != null && it.calendarId in visible }
        val now = LocalDateTime.now()
        val due = Cal.occurrences(events, now.minusDays(1), now.plusDays(2))
            .map { it to it.start.minusMinutes(it.event.reminder!!.toLong()) }
            .filter { it.second.isAfter(now) }
            .sortedBy { it.second }
            .take(MAX)
        due.forEachIndexed { i, (o, at) ->
            val when_ = if (o.event.allDay) "весь день" else "%02d:%02d–%02d:%02d".format(o.start.hour, o.start.minute, o.end.hour, o.end.minute)
            val intent = Intent(ctx, ReminderReceiver::class.java)
                .putExtra("title", o.event.title.ifEmpty { "(без названия)" })
                .putExtra("text", when_ + if (o.event.location.isNotEmpty()) ", ${o.event.location}" else "")
                .putExtra("id", i)
            val pi = PendingIntent.getBroadcast(ctx, i, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            val ms = at.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            val exact = Build.VERSION.SDK_INT < Build.VERSION_CODES.S || am.canScheduleExactAlarms()
            if (exact) am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, ms, pi)
            else am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, ms, pi)
        }
    }
}

class ReminderReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val open = PendingIntent.getActivity(ctx, 0, Intent(ctx, MainActivity::class.java).putExtra("open", "calendar")
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP), PendingIntent.FLAG_IMMUTABLE)
        val n = NotificationCompat.Builder(ctx, Reminders.CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_calendar)
            .setContentTitle(intent.getStringExtra("title"))
            .setContentText(intent.getStringExtra("text"))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_EVENT)
            .setAutoCancel(true)
            .setContentIntent(open)
            .build()
        ctx.getSystemService(NotificationManager::class.java)
            .notify(1000 + intent.getIntExtra("id", 0) + (System.currentTimeMillis() % 100000).toInt(), n)
    }
}

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        Reminders.schedule(ctx)
    }
}
