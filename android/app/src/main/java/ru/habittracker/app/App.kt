package ru.habittracker.app

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.ProcessLifecycleOwner
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONObject
import ru.habittracker.app.data.Db
import ru.habittracker.app.data.Repo
import ru.habittracker.app.data.Sync
import ru.habittracker.app.data.SyncError
import ru.habittracker.app.data.WebDav
import ru.habittracker.app.work.Reminders
import ru.habittracker.app.work.SyncWorker

class App : Application() {
    lateinit var repo: Repo
    lateinit var sync: SyncManager

    /** Счётчик изменений: экраны перечитывают данные, когда он меняется. */
    var version by mutableIntStateOf(0)

    override fun onCreate() {
        super.onCreate()
        instance = this
        ru.habittracker.app.ui.Appearance.load(this)
        repo = Repo(Db(this))
        sync = SyncManager(this)
        repo.onChange = {
            version++
            Reminders.schedule(this)
            sync.scheduleAfterEdit()
        }
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(Reminders.CHANNEL, "Напоминания календаря",
            NotificationManager.IMPORTANCE_HIGH).apply { description = "Напоминания о событиях календаря" })
        Reminders.schedule(this)
        SyncWorker.schedule(this)
        // синхронизация при открытии приложения и при уходе с экрана
        ProcessLifecycleOwner.get().lifecycle.addObserver(LifecycleEventObserver { _, e ->
            if (e == Lifecycle.Event.ON_START || e == Lifecycle.Event.ON_STOP) sync.runNow()
        })
    }

    companion object {
        lateinit var instance: App
            private set
    }
}

/** Настройки синхронизации — в личном хранилище приложения (недоступно другим приложениям). */
class SyncManager(private val app: App) {
    private val prefs = app.getSharedPreferences("sync", Context.MODE_PRIVATE)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val mutex = Mutex()
    private var pending: Job? = null

    var status by mutableStateOf(prefs.getString("status", "") ?: "")
    var ok by mutableStateOf(prefs.getBoolean("status_ok", true))
    var busy by mutableStateOf(false)

    val login get() = prefs.getString("login", "") ?: ""
    val deviceName get() = prefs.getString("device_name", "Телефон") ?: "Телефон"
    val enabled get() = prefs.getBoolean("enabled", false) && login.isNotEmpty()
    val lastSync get() = prefs.getString("last_sync", null)

    fun configure(login: String, password: String?, deviceName: String) {
        prefs.edit().putString("login", login.trim())
            .apply { if (!password.isNullOrBlank()) putString("password", password.replace(" ", "")) }
            .putString("device_name", deviceName.trim().ifEmpty { "Телефон" })
            .putBoolean("enabled", true).remove("cache").apply()
    }

    fun disable() { prefs.edit().putBoolean("enabled", false).apply() }

    private fun setStatus(text: String, good: Boolean) {
        status = text; ok = good
        prefs.edit().putString("status", text).putBoolean("status_ok", good).apply()
    }

    fun scheduleAfterEdit() {
        if (!enabled || busy) return
        pending?.cancel()
        pending = scope.launch { delay(20_000); runNow() }
    }

    fun runNow() { scope.launch { syncNow() } }

    /** Скачать → слить → отправить. Безопасно вызывать откуда угодно (в т.ч. из WorkManager). */
    suspend fun syncNow(): Boolean = mutex.withLock {
        if (!enabled) return false
        withContext(Dispatchers.Main) { busy = true; setStatus("Синхронизация…", true) }
        try {
            val result = withContext(Dispatchers.IO) {
                val dav = WebDav(prefs.getString("url", null) ?: WebDav.YANDEX_URL, login, prefs.getString("password", "") ?: "")
                val device = app.repo.deviceId()
                val cacheJson = JSONObject(prefs.getString("cache", "{}") ?: "{}")
                val cache = cacheJson.keys().asSequence().associateWith { cacheJson.getString(it) }
                val (payloads, newCache) = dav.fetchRemote(device, cache)
                val stats = Sync.mergeAll(app.repo.db, payloads, device)
                val blob = Sync.encode(Sync.export(app.repo.db, device, deviceName))
                dav.put(WebDav.deviceFile(device), blob)
                // вложения заметок: свои новые — на Диск, недостающие — к себе
                if (stats.changed) ru.habittracker.app.data.Attachments.cleanup(app, app.repo)
                val wanted = app.repo.attachments().map { it.file }.toSet()
                if (wanted.isNotEmpty()) {
                    val files = WebDav(prefs.getString("url", null) ?: WebDav.YANDEX_URL, login, prefs.getString("password", "") ?: "",
                        WebDav.FOLDER + "/files")
                    val (_, down) = ru.habittracker.app.data.Attachments.syncFiles(files, ru.habittracker.app.data.Attachments.folder(app), wanted)
                    if (down > 0) withContext(Dispatchers.Main) { app.version++ }
                }
                prefs.edit().putString("cache", JSONObject(newCache as Map<*, *>).toString())
                    .putString("last_sync", Sync.nowTs()).apply()
                stats
            }
            withContext(Dispatchers.Main) {
                if (result.changed) { app.version++; Reminders.schedule(app) }
                val parts = listOfNotNull(
                    if (result.added > 0) "добавлено ${result.added}" else null,
                    if (result.updated > 0) "обновлено ${result.updated}" else null,
                    if (result.deleted > 0) "удалено ${result.deleted}" else null)
                setStatus("Синхронизировано" + if (parts.isEmpty()) "" else ": " + parts.joinToString(", "), true)
            }
            true
        } catch (e: SyncError) {
            withContext(Dispatchers.Main) { setStatus(e.message ?: "Ошибка синхронизации", false) }
            false
        } catch (e: Exception) {
            withContext(Dispatchers.Main) { setStatus("Не удалось синхронизировать: ${e.message}", false) }
            false
        } finally {
            withContext(Dispatchers.Main) { busy = false }
        }
    }
}
