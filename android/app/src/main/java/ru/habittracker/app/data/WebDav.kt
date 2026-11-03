package ru.habittracker.app.data

import okhttp3.Credentials
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import org.w3c.dom.Element
import java.io.IOException
import java.net.URLDecoder
import java.net.URLEncoder
import java.util.concurrent.TimeUnit
import javax.xml.parsers.DocumentBuilderFactory

class SyncError(message: String) : Exception(message)

/** Яндекс Диск по WebDAV — как desktop/tracker/webdav.py. */
class WebDav(private val base: String, login: String, password: String, private val folder: String = FOLDER) {
    companion object {
        const val YANDEX_URL = "https://webdav.yandex.ru"
        const val FOLDER = "HabitTracker-sync"
        fun deviceFile(deviceId: String) = "device-$deviceId.json.gz"
    }

    private val auth = Credentials.basic(login, password, Charsets.UTF_8)
    private val client = OkHttpClient.Builder().connectTimeout(25, TimeUnit.SECONDS)
        .readTimeout(25, TimeUnit.SECONDS).writeTimeout(25, TimeUnit.SECONDS).build()

    private fun url(name: String = ""): String {
        val enc = { s: String -> URLEncoder.encode(s, "UTF-8").replace("+", "%20") }
        return base.trimEnd('/') + "/" + enc(folder) + "/" + (if (name.isEmpty()) "" else enc(name))
    }

    private fun call(method: String, url: String, body: ByteArray? = null, headers: Map<String, String> = emptyMap(),
                     type: String = "application/octet-stream"): Pair<Int, ByteArray> {
        val rb = body?.toRequestBody(type.toMediaType())
        val req = Request.Builder().url(url).method(method, rb ?: if (method == "PUT") ByteArray(0).toRequestBody() else null)
            .header("Authorization", auth).header("User-Agent", "HabitTracker-Android/1.0")
        headers.forEach { (k, v) -> req.header(k, v) }
        try {
            client.newCall(req.build()).execute().use { r -> return r.code to (r.body?.bytes() ?: ByteArray(0)) }
        } catch (e: IOException) {
            throw SyncError("Нет соединения с Яндекс Диском. Проверьте интернет.")
        }
    }

    private fun check(code: Int, what: String) {
        when {
            code == 401 -> throw SyncError("Яндекс Диск не принял логин или пароль приложения. Проверьте их в настройках.")
            code == 403 -> throw SyncError("Яндекс Диск запретил доступ. Создайте пароль приложения для «Файлов» (WebDAV).")
            code == 507 -> throw SyncError("На Яндекс Диске закончилось место.")
            code >= 400 -> throw SyncError("Яндекс Диск ответил ошибкой $code ($what).")
        }
    }

    fun ensureFolder() {
        val (code, _) = call("MKCOL", url())
        if (code !in listOf(201, 405, 409)) check(code, "создание папки")
    }

    data class RemoteFile(val name: String, val etag: String)

    fun list(): List<RemoteFile> {
        val body = """<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:getetag/><d:resourcetype/></d:prop></d:propfind>"""
        val (code, bytes) = call("PROPFIND", url(), body.toByteArray(), mapOf("Depth" to "1"), "application/xml")
        if (code == 404) return emptyList()
        check(code, "список файлов")
        val f = DocumentBuilderFactory.newInstance().apply { isNamespaceAware = true }
        val doc = f.newDocumentBuilder().parse(bytes.inputStream())
        val out = mutableListOf<RemoteFile>()
        val responses = doc.getElementsByTagNameNS("DAV:", "response")
        for (i in 0 until responses.length) {
            val r = responses.item(i) as Element
            val href = URLDecoder.decode(r.getElementsByTagNameNS("DAV:", "href").item(0)?.textContent ?: "", "UTF-8")
            val name = href.trimEnd('/').substringAfterLast('/')
            if (r.getElementsByTagNameNS("DAV:", "collection").length > 0) continue
            val etag = (r.getElementsByTagNameNS("DAV:", "getetag").item(0)?.textContent ?: "").trim('"')
            out += RemoteFile(name, etag)
        }
        return out
    }

    fun get(name: String): ByteArray { val (code, b) = call("GET", url(name)); check(code, "загрузка $name"); return b }

    fun put(name: String, data: ByteArray) { val (code, _) = call("PUT", url(name), data); check(code, "отправка $name") }

    /** Скачать изменившиеся файлы других устройств (cache: имя → etag). */
    fun fetchRemote(ownDevice: String, cache: Map<String, String>): Pair<List<JSONObject>, Map<String, String>> {
        ensureFolder()
        val payloads = mutableListOf<JSONObject>()
        val newCache = mutableMapOf<String, String>()
        for (f in list()) {
            if (!f.name.startsWith("device-") || f.name == deviceFile(ownDevice)) continue
            newCache[f.name] = f.etag
            if (f.etag.isNotEmpty() && cache[f.name] == f.etag) continue
            try {
                payloads += Sync.decode(get(f.name))
            } catch (e: SyncError) {
                throw e
            } catch (e: Exception) {
                throw SyncError("Файл ${f.name} на Диске повреждён или от новой версии программы.")
            }
        }
        return payloads to newCache
    }
}
