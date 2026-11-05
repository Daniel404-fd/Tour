package ru.habittracker.app.ui

import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.InsertDriveFile
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.outlined.AttachFile
import androidx.compose.material.icons.outlined.PictureAsPdf
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import ru.habittracker.app.App
import ru.habittracker.app.ConfirmDialog
import ru.habittracker.app.data.Attachment
import ru.habittracker.app.data.Attachments
import ru.habittracker.app.useData
import java.io.File

private fun decodeSampled(f: File, maxSide: Int): Bitmap? {
    val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeFile(f.path, o)
    if (o.outWidth <= 0) return null
    var s = 1
    while (o.outWidth / (s * 2) >= maxSide && o.outHeight / (s * 2) >= maxSide) s *= 2
    return BitmapFactory.decodeFile(f.path, BitmapFactory.Options().apply { inSampleSize = s })
}

/** Вложения заметки: миниатюры + «Прикрепить». Касание — просмотр, долгое — удалить. */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun AttachmentsRow(noteId: Long) {
    val repo = App.instance.repo
    val ctx = LocalContext.current
    val t = tok
    val items = useData { repo.attachments(noteId) }
    var open by remember { mutableStateOf<Int?>(null) }
    var delete by remember { mutableStateOf<Attachment?>(null) }
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        for (u in uris) try { Attachments.addFromUri(ctx, repo, noteId, u) } catch (e: Exception) {
            Toast.makeText(ctx, e.message ?: "Не удалось прикрепить файл", Toast.LENGTH_LONG).show()
        }
        if (uris.isNotEmpty()) App.instance.sync.scheduleAfterEdit()
    }
    Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (items.isNotEmpty()) Caption("Вложения · ${items.size}", modifier = Modifier.weight(1f)) else Spacer(Modifier.weight(1f))
            TextButton(onClick = { pick.launch(arrayOf("*/*")) }) {
                Icon(Icons.Outlined.AttachFile, null); Spacer(Modifier.width(4.dp)); Text("Прикрепить файл или фото")
            }
        }
        if (items.isNotEmpty()) Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items.forEachIndexed { i, a ->
                val f = Attachments.file(ctx, a)
                Box(Modifier.size(84.dp).clip(RoundedCornerShape(10.dp)).background(t.surface2)
                    .border(1.dp, t.border, RoundedCornerShape(10.dp))
                    .combinedClickable(onClick = { open = i }, onLongClick = { delete = a }, onLongClickLabel = "Удалить"),
                    contentAlignment = Alignment.Center) {
                    val thumb by produceState<Bitmap?>(null, a.file, f.exists()) {
                        value = if (Attachments.kind(a.name) == "image" && f.exists()) withContext(Dispatchers.IO) { decodeSampled(f, 200) } else null
                    }
                    if (thumb != null) Image(thumb!!.asImageBitmap(), a.name, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
                    else Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(6.dp)) {
                        Icon(if (Attachments.kind(a.name) == "pdf") Icons.Outlined.PictureAsPdf else Icons.AutoMirrored.Outlined.InsertDriveFile,
                            null, tint = t.text2)
                        Text(if (f.exists()) a.name else "загружается…", fontSize = 11.sp, color = t.text2, maxLines = 2,
                            overflow = TextOverflow.Ellipsis, textAlign = TextAlign.Center)
                    }
                }
            }
        }
    }
    open?.let { AttachmentViewer(items, it) { open = null } }
    delete?.let { a -> ConfirmDialog("Удалить вложение", "Удалить «${a.name}» из заметки?", "Удалить",
        { Attachments.remove(ctx, repo, a) }, { delete = null }) }
}

/** Просмотр во весь экран: фото — щипком увеличить, PDF — страницы подряд, текст — как текст.
 *  Листается вбок между вложениями заметки. */
@Composable
fun AttachmentViewer(items: List<Attachment>, start: Int, onClose: () -> Unit) {
    val ctx = LocalContext.current
    val pager = rememberPagerState(start) { items.size }
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Column(Modifier.fillMaxSize().background(Color(0xFF111111))) {
            val a = items[pager.currentPage]
            Row(Modifier.fillMaxWidth().statusBarsPadding().padding(4.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = onClose) { Icon(Icons.Filled.Close, "Закрыть", tint = Color.White) }
                Column(Modifier.weight(1f)) {
                    Text(a.name, color = Color.White, maxLines = 1, overflow = TextOverflow.Ellipsis, fontSize = 16.sp)
                    Text(Attachments.humanSize(a.size) + if (items.size > 1) " · ${pager.currentPage + 1} из ${items.size}" else "",
                        color = Color(0xFFBBBBBB), fontSize = 12.sp)
                }
                IconButton(onClick = { share(ctx, a, Intent.ACTION_SEND) }) { Icon(Icons.Outlined.Share, "Поделиться", tint = Color.White) }
            }
            HorizontalPager(pager, Modifier.fillMaxSize()) { page ->
                val item = items[page]
                val f = Attachments.file(ctx, item)
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    when {
                        !f.exists() -> Message("Файл ещё не загрузился с Яндекс Диска — он появится после синхронизации.")
                        Attachments.kind(item.name) == "image" -> ZoomImage(f)
                        Attachments.kind(item.name) == "pdf" -> PdfPages(f)
                        Attachments.kind(item.name) == "text" -> {
                            val txt = remember(f) { runCatching { f.readBytes().take(2_000_000).toByteArray().toString(Charsets.UTF_8) }.getOrDefault("") }
                            Text(txt, color = Color(0xFFEEEEEE), fontFamily = FontFamily.Monospace, fontSize = 13.sp,
                                modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp))
                        }
                        else -> Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Message("Этот файл здесь не показать.")
                            OutlinedButton(onClick = { share(ctx, item, Intent.ACTION_VIEW) }) { Text("Открыть в другом приложении", color = Color.White) }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun Message(text: String) = Text(text, color = Color(0xFFDDDDDD), textAlign = TextAlign.Center, modifier = Modifier.padding(24.dp))

@Composable
private fun ZoomImage(f: File) {
    val bmp by produceState<Bitmap?>(null, f) { value = withContext(Dispatchers.IO) { decodeSampled(f, 2048) } }
    var scale by remember { mutableFloatStateOf(1f) }
    var ox by remember { mutableFloatStateOf(0f) }
    var oy by remember { mutableFloatStateOf(0f) }
    bmp?.let { b ->
        Image(b.asImageBitmap(), null, Modifier.fillMaxSize()
            .pointerInput(Unit) {
                detectTransformGestures { _, pan, zoom, _ ->
                    scale = (scale * zoom).coerceIn(1f, 6f)
                    if (scale > 1f) { ox += pan.x; oy += pan.y } else { ox = 0f; oy = 0f }
                }
            }
            .graphicsLayer(scaleX = scale, scaleY = scale, translationX = ox, translationY = oy),
            contentScale = ContentScale.Fit)
    } ?: Message("Не удалось открыть изображение.")
}

@Composable
private fun PdfPages(f: File) {
    val pages by produceState<List<Bitmap>?>(null, f) {
        value = withContext(Dispatchers.IO) {
            runCatching {
                ParcelFileDescriptor.open(f, ParcelFileDescriptor.MODE_READ_ONLY).use { fd ->
                    PdfRenderer(fd).use { r ->
                        (0 until minOf(r.pageCount, 60)).map { i ->
                            r.openPage(i).use { p ->
                                val w = 1200
                                val h = (w * p.height / p.width.toFloat()).toInt()
                                Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888).also { bm ->
                                    bm.eraseColor(android.graphics.Color.WHITE)
                                    p.render(bm, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                                }
                            }
                        }
                    }
                }
            }.getOrNull() ?: emptyList()
        }
    }
    when {
        pages == null -> Message("Открываю…")
        pages!!.isEmpty() -> Message("Не удалось открыть PDF.")
        else -> LazyColumn(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(pages!!.size) { i -> Image(pages!![i].asImageBitmap(), "Страница ${i + 1}", Modifier.fillMaxWidth(), contentScale = ContentScale.FillWidth) }
        }
    }
}

private fun share(ctx: android.content.Context, a: Attachment, action: String) {
    val f = Attachments.file(ctx, a)
    if (!f.exists()) return
    val uri = FileProvider.getUriForFile(ctx, "ru.habittracker.app.files", f)
    val i = Intent(action).apply {
        if (action == Intent.ACTION_SEND) { putExtra(Intent.EXTRA_STREAM, uri); type = a.mime.ifEmpty { "*/*" } }
        else setDataAndType(uri, a.mime.ifEmpty { "*/*" })
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    runCatching { ctx.startActivity(Intent.createChooser(i, if (action == Intent.ACTION_SEND) "Поделиться" else "Открыть с помощью")) }
}
