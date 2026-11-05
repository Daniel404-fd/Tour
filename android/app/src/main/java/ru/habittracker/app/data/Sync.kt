package ru.habittracker.app.data

import android.content.ContentValues
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.security.MessageDigest
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.zip.GZIPInputStream
import java.util.zip.GZIPOutputStream

/**
 * Слияние по записям — точная копия desktop/tracker/sync.py (формат 1).
 * Каждое устройство пишет только свой файл; побеждает более позднее изменение;
 * удаление побеждает, если оно позже последней правки.
 */
object Sync {
    const val FORMAT = 1

    class Stats { var added = 0; var updated = 0; var deleted = 0; val changed get() = added + updated + deleted > 0 }

    private val tsFmt = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").withZone(ZoneOffset.UTC)
    fun nowTs(): String = tsFmt.format(Instant.now())

    private fun q(n: String) = "\"$n\""

    private fun cursorValue(c: Cursor, i: Int): Any = when (c.getType(i)) {
        Cursor.FIELD_TYPE_NULL -> JSONObject.NULL
        Cursor.FIELD_TYPE_INTEGER -> c.getLong(i)
        Cursor.FIELD_TYPE_FLOAT -> c.getDouble(i)
        else -> c.getString(i)
    }

    // ---------------------------------------------------------------- экспорт
    fun export(db: SQLiteDatabase, deviceId: String, deviceName: String): JSONObject {
        val uidOf = mutableMapOf<String, Map<Long, String>>()
        val records = JSONObject()
        for ((table, spec) in SyncSchema.TABLES) {
            val (fields, refs) = spec
            val key = if (table == "habit_marks") "rowid" else "id"
            val map = mutableMapOf<Long, String>()
            val arr = JSONArray()
            db.rawQuery("SELECT $key, sync_uid, sync_ts, ${fields.joinToString(", ") { q(it) }} FROM $table", null).use { c ->
                while (c.moveToNext()) {
                    map[c.getLong(0)] = c.getString(1)
                    val data = JSONObject()
                    fields.forEachIndexed { i, f ->
                        var v = cursorValue(c, 3 + i)
                        val ref = refs[f]
                        if (ref != null && v != JSONObject.NULL) v = uidOf[ref]?.get((v as Number).toLong()) ?: JSONObject.NULL
                        data.put(f, v)
                    }
                    arr.put(JSONObject().put("uid", c.getString(1)).put("ts", c.getString(2)).put("data", data))
                }
            }
            uidOf[table] = map
            records.put(table, arr)
        }
        val tombs = JSONArray()
        db.rawQuery("SELECT uid, tbl, ts FROM sync_tombstones", null).use { c ->
            while (c.moveToNext()) tombs.put(JSONObject().put("uid", c.getString(0)).put("table", c.getString(1)).put("ts", c.getString(2)))
        }
        return JSONObject().put("format", FORMAT).put("device", deviceId).put("device_name", deviceName)
            .put("generated", nowTs()).put("records", records).put("tombstones", tombs)
    }

    fun encode(payload: JSONObject): ByteArray {
        val out = ByteArrayOutputStream()
        GZIPOutputStream(out).use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
        return out.toByteArray()
    }

    fun decode(blob: ByteArray): JSONObject {
        val text = GZIPInputStream(ByteArrayInputStream(blob)).use { it.readBytes() }.toString(Charsets.UTF_8)
        val o = JSONObject(text)
        require(o.optInt("format") == FORMAT) { "Неизвестный формат файла синхронизации" }
        return o
    }

    // ---------------------------------------------------------------- слияние
    /** Каноническая форма (как json.dumps(sort_keys=True) в Python) — для одинакового выбора при равном времени. */
    private fun canonical(o: JSONObject): String {
        val keys = o.keys().asSequence().toList().sorted()
        return keys.joinToString(", ", "{", "}") { k ->
            val v = o.get(k)
            JSONObject.quote(k) + ": " + when (v) {
                JSONObject.NULL -> "null"
                is String -> pyQuote(v)
                is Double -> pyFloat(v)
                is Float -> pyFloat(v.toDouble())
                is Number -> v.toString()
                is Boolean -> if (v) "true" else "false"
                else -> pyQuote(v.toString())
            }
        }
    }

    /** json.dumps(ensure_ascii=False) экранирует только \" \\ и управляющие символы. */
    private fun pyQuote(s: String): String {
        val sb = StringBuilder("\"")
        for (ch in s) when {
            ch == '"' -> sb.append("\\\"")
            ch == '\\' -> sb.append("\\\\")
            ch == '\n' -> sb.append("\\n")
            ch == '\r' -> sb.append("\\r")
            ch == '\t' -> sb.append("\\t")
            ch == '\b' -> sb.append("\\b")
            ch == '\u000C' -> sb.append("\\f")
            ch < ' ' -> sb.append("\\u%04x".format(ch.code))
            else -> sb.append(ch)
        }
        return sb.append('"').toString()
    }

    private fun pyFloat(d: Double): String {
        if (d == Math.floor(d) && !d.isInfinite() && Math.abs(d) < 1e16) return "%.1f".format(java.util.Locale.ROOT, d)
        return d.toString()
    }

    fun digest(o: JSONObject): String {
        val md = MessageDigest.getInstance("SHA-1").digest(canonical(o).toByteArray(Charsets.UTF_8))
        return md.joinToString("") { "%02x".format(it) }
    }

    private fun localCanon(db: SQLiteDatabase, table: String, key: String, rid: Long): JSONObject {
        val (fields, refs) = SyncSchema.TABLES.getValue(table)
        val data = JSONObject()
        db.rawQuery("SELECT ${fields.joinToString(", ") { q(it) }} FROM $table WHERE $key = ?", arrayOf(rid.toString())).use { c ->
            if (c.moveToFirst()) fields.forEachIndexed { i, f ->
                var v = cursorValue(c, i)
                val ref = refs[f]
                if (ref != null && v != JSONObject.NULL) {
                    v = db.rawQuery("SELECT sync_uid FROM $ref WHERE id = ?", arrayOf((v as Number).toString())).use { r ->
                        if (r.moveToFirst()) r.getString(0) else JSONObject.NULL
                    }
                }
                data.put(f, v)
            }
        }
        return data
    }

    private fun put(cv: ContentValues, k: String, v: Any?) {
        when (v) {
            null, JSONObject.NULL -> cv.putNull(k)
            is Int -> cv.put(k, v.toLong())
            is Long -> cv.put(k, v)
            is Double -> cv.put(k, v)
            is Float -> cv.put(k, v.toDouble())
            is Boolean -> cv.put(k, if (v) 1L else 0L)
            else -> cv.put(k, v.toString())
        }
    }

    fun merge(db: SQLiteDatabase, payload: JSONObject, stats: Stats = Stats()): Stats {
        val localTombs = mutableMapOf<String, String>()
        db.rawQuery("SELECT uid, ts FROM sync_tombstones", null).use { c -> while (c.moveToNext()) localTombs[c.getString(0)] = c.getString(1) }
        val remoteTombs = mutableMapOf<String, JSONObject>()
        payload.optJSONArray("tombstones")?.let { a -> for (i in 0 until a.length()) a.getJSONObject(i).let { remoteTombs[it.getString("uid")] = it } }
        val records = payload.optJSONObject("records") ?: JSONObject()

        for ((table, spec) in SyncSchema.TABLES) {
            val (fields, refs) = spec
            val key = if (table == "habit_marks") "rowid" else "id"
            val local = mutableMapOf<String, Pair<Long, String?>>()
            db.rawQuery("SELECT sync_uid, $key, sync_ts FROM $table", null).use { c ->
                while (c.moveToNext()) local[c.getString(0)] = c.getLong(1) to (if (c.isNull(2)) null else c.getString(2))
            }
            val arr = records.optJSONArray(table) ?: continue
            for (i in 0 until arr.length()) {
                val rec = arr.getJSONObject(i)
                val uid = rec.getString("uid"); val ts = rec.getString("ts")
                val data = rec.getJSONObject("data")
                val remoteDeleted = remoteTombs[uid]?.getString("ts")
                if (remoteDeleted != null && remoteDeleted >= ts) continue
                val localDeleted = localTombs[uid]
                if (localDeleted != null && localDeleted >= ts) continue      // у нас удалено позже
                val values = mutableMapOf<String, Any?>()
                var ok = true
                // поля, которых нет в файле (прежняя версия программы), не трогаем
                for (f in fields) {
                    if (!data.has(f)) continue
                    var v: Any? = data.get(f)
                    val ref = refs[f]
                    if (ref != null && v != JSONObject.NULL) {
                        val id = db.rawQuery("SELECT id FROM $ref WHERE sync_uid = ?", arrayOf(v.toString())).use { c -> if (c.moveToFirst()) c.getLong(0) else null }
                        if (id == null) { if ("$table.$f" in SyncSchema.REQUIRED_REFS) { ok = false; break }; v = JSONObject.NULL } else v = id
                    }
                    values[f] = v
                }
                if (!ok) continue
                val cur = local[uid]
                if (cur == null) {
                    if (table == "habit_marks") db.execSQL("DELETE FROM habit_marks WHERE habit_id = ? AND day = ? AND sync_uid IS NOT ?",
                        arrayOf(values["habit_id"], values["day"], uid))
                    val cv = ContentValues()
                    for ((f, v) in values) put(cv, f, v)
                    cv.put("sync_uid", uid); cv.put("sync_ts", ts)
                    db.insertOrThrow(table, null, cv)
                    stats.added++
                } else {
                    val curTs = cur.second ?: ""
                    val wins = ts > curTs || (ts == curTs && digest(data) > digest(localCanon(db, table, key, cur.first)))
                    if (wins) {
                        val cv = ContentValues()
                        for ((f, v) in values) put(cv, f, v)
                        cv.put("sync_ts", ts)
                        db.update(table, cv, "$key = ?", arrayOf(cur.first.toString()))
                        stats.updated++
                    }
                }
            }
        }
        // удаления: сначала «дети»
        for (table in SyncSchema.TABLES.keys.reversed()) {
            val key = if (table == "habit_marks") "rowid" else "id"
            for (t in remoteTombs.values.filter { it.getString("table") == table }) {
                val uid = t.getString("uid"); val ts = t.getString("ts")
                val row = db.rawQuery("SELECT $key, sync_ts FROM $table WHERE sync_uid = ?", arrayOf(uid)).use { c ->
                    if (c.moveToFirst()) c.getLong(0) to (if (c.isNull(1)) "" else c.getString(1)) else null
                }
                if (row != null && row.second <= ts) {
                    db.execSQL("DELETE FROM $table WHERE $key = ?", arrayOf(row.first))
                    db.execSQL("UPDATE sync_tombstones SET ts = ? WHERE uid = ?", arrayOf(ts, uid))
                    stats.deleted++
                } else if (row == null) {
                    val existing = db.rawQuery("SELECT ts FROM sync_tombstones WHERE uid = ?", arrayOf(uid)).use { c -> if (c.moveToFirst()) c.getString(0) else null }
                    if (existing == null) db.execSQL("INSERT INTO sync_tombstones(uid, tbl, ts) VALUES (?, ?, ?)", arrayOf(uid, table, ts))
                    else if (ts > existing) db.execSQL("UPDATE sync_tombstones SET ts = ? WHERE uid = ?", arrayOf(ts, uid))
                }
            }
        }
        return stats
    }

    /** Слить данные других устройств одной транзакцией. */
    fun mergeAll(db: SQLiteDatabase, payloads: List<JSONObject>, ownDevice: String): Stats {
        val stats = Stats()
        db.beginTransaction()
        try {
            for (p in payloads) if (p.optString("device") != ownDevice) merge(db, p, stats)
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        return stats
    }
}
