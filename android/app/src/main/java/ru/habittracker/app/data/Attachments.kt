package ru.habittracker.app.data

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import android.webkit.MimeTypeMap
import java.io.File
import java.util.UUID

/** Вложения заметок — как desktop/tracker/attachments.py: файл в папке приложения, запись в базе,
 *  файлы синхронизируются через «HabitTracker-sync/files» на Яндекс Диске. */
object Attachments {
    const val MAX_SIZE = 50L * 1024 * 1024
    private val IMAGE = setOf("png", "jpg", "jpeg", "gif", "bmp", "webp", "heic", "heif")
    private val TEXT = setOf("txt", "md", "csv", "json", "log", "xml", "ini", "py", "yaml", "yml", "html")

    class TooBig(name: String) : Exception("Файл «$name» больше 50 МБ — такие лучше хранить в облаке и вставить ссылку.")

    fun folder(ctx: Context) = File(ctx.filesDir, "attachments").apply { mkdirs() }
    fun file(ctx: Context, a: Attachment) = File(folder(ctx), a.file)

    fun kind(name: String): String {
        val ext = name.substringAfterLast('.', "").lowercase()
        return when { ext in IMAGE -> "image"; ext == "pdf" -> "pdf"; ext in TEXT -> "text"; else -> "file" }
    }

    fun humanSize(n: Long): String = when {
        n >= 1L shl 30 -> "%.1f ГБ".format(n / (1L shl 30).toDouble())
        n >= 1L shl 20 -> "%.1f МБ".format(n / (1L shl 20).toDouble())
        n >= 1L shl 10 -> "%.0f КБ".format(n / (1L shl 10).toDouble())
        else -> "$n Б"
    }.replace(".", ",")

    fun addFromUri(ctx: Context, repo: Repo, noteId: Long, uri: Uri): Long {
        val cr = ctx.contentResolver
        var name = "файл"
        var size = -1L
        cr.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { c ->
            if (c.moveToFirst()) {
                c.getString(0)?.let { name = it }
                if (!c.isNull(1)) size = c.getLong(1)
            }
        }
        if (size > MAX_SIZE) throw TooBig(name)
        val data = cr.openInputStream(uri)?.use { it.readBytes() } ?: throw IllegalStateException("Не удалось прочитать «$name»")
        if (data.size > MAX_SIZE) throw TooBig(name)
        val mime = cr.getType(uri) ?: MimeTypeMap.getSingleton().getMimeTypeFromExtension(name.substringAfterLast('.', "").lowercase())
            ?: "application/octet-stream"
        if (!name.contains('.')) MimeTypeMap.getSingleton().getExtensionFromMimeType(mime)?.let { name = "$name.$it" }
        return addBytes(ctx, repo, noteId, data, name, mime)
    }

    fun addBytes(ctx: Context, repo: Repo, noteId: Long, data: ByteArray, name: String, mime: String = "application/octet-stream"): Long {
        val ext = name.substringAfterLast('.', "").lowercase().take(9)
        val stored = UUID.randomUUID().toString().replace("-", "") + if (ext.isNotEmpty()) ".$ext" else ""
        val tmp = File(folder(ctx), "$stored.part")
        tmp.writeBytes(data)
        tmp.renameTo(File(folder(ctx), stored))
        return repo.addAttachment(noteId, name, stored, data.size.toLong(), mime)
    }

    fun remove(ctx: Context, repo: Repo, a: Attachment) {
        repo.deleteAttachment(a.id)
        if (repo.attachments().none { it.file == a.file }) File(folder(ctx), a.file).delete()
    }

    /** Файлы без записей (заметку удалили на другом устройстве) — убрать. */
    fun cleanup(ctx: Context, repo: Repo): Int {
        val wanted = repo.attachments().map { it.file }.toSet()
        return folder(ctx).listFiles()?.count { it.isFile && it.name !in wanted && !it.name.endsWith(".part") && it.delete() } ?: 0
    }

    /** Отправить свои новые файлы и скачать недостающие (в фоне, после синхронизации данных). */
    fun syncFiles(files: WebDav, dir: File, wanted: Set<String>): Pair<Int, Int> {
        val remote = files.list().map { it.name }.toSet()
        if (remote.isEmpty()) files.ensureFolder()
        var up = 0; var down = 0
        dir.mkdirs()
        for (name in wanted.sorted()) {
            val f = File(dir, name)
            if (f.exists() && name !in remote) { files.put(name, f.readBytes()); up++ }
            else if (!f.exists() && name in remote) {
                val tmp = File(dir, "$name.part"); tmp.writeBytes(files.get(name)); tmp.renameTo(f); down++
            }
        }
        return up to down
    }
}
