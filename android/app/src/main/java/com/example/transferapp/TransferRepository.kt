package com.example.transferapp

import android.content.ContentResolver
import android.content.Context
import android.net.Uri
import android.os.Environment
import androidx.documentfile.provider.DocumentFile
import io.ktor.client.call.body
import io.ktor.client.plugins.websocket.webSocket
import io.ktor.client.request.forms.MultiPartFormDataContent
import io.ktor.client.request.forms.formData
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsChannel
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.content.PartData
import io.ktor.http.contentType
import io.ktor.utils.io.readRemaining
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream

class TransferRepository(private val context: Context) {
    private val client = NetworkModule.http

    suspend fun pair(serverUrl: String, token: String, deviceName: String): PairResponse {
        return client.post("$serverUrl/api/pair") {
            contentType(ContentType.Application.Json)
            setBody(PairRequest(token, deviceName))
        }.body()
    }

    suspend fun fetchJobs(serverUrl: String, deviceToken: String): JobsResponse {
        return client.get("$serverUrl/api/phone/jobs") {
            url {
                parameters.append("device_token", deviceToken)
            }
        }.body()
    }

    suspend fun initUpload(serverUrl: String, req: UploadInitRequest): UploadInitResponse {
        return client.post("$serverUrl/api/phone/upload/init") {
            contentType(ContentType.Application.Json)
            setBody(req)
        }.body()
    }

    suspend fun uploadFileChunked(
        serverUrl: String,
        deviceToken: String,
        fileUri: Uri,
        chunkSize: Int = 1024 * 1024,
        onProgress: suspend (sent: Int, total: Int) -> Unit,
    ) {
        val resolver = context.contentResolver
        val fileName = queryFileName(resolver, fileUri) ?: "upload.bin"
        val mime = resolver.getType(fileUri) ?: "application/octet-stream"
        val size = queryFileSize(resolver, fileUri)

        val init = initUpload(
            serverUrl,
            UploadInitRequest(
                deviceToken = deviceToken,
                filename = fileName,
                sizeBytes = size,
                chunkSize = chunkSize,
                mimeType = mime,
            )
        )
        require(init.ok && init.transferId != null && init.totalChunks != null)

        val transferId = init.transferId
        val totalChunks = init.totalChunks

        val status: UploadStatusResponse = client.get("$serverUrl/api/phone/upload/status/$transferId") {
            url { parameters.append("device_token", deviceToken) }
        }.body()
        val uploadedSet = status.uploadedChunks.toSet()

        withContext(Dispatchers.IO) {
            resolver.openInputStream(fileUri).use { input ->
                requireNotNull(input)
                val allBytes = input.readBytes()
                for (index in 0 until totalChunks) {
                    if (uploadedSet.contains(index)) {
                        onProgress(index + 1, totalChunks)
                        continue
                    }
                    val start = index * chunkSize
                    val end = minOf(start + chunkSize, allBytes.size)
                    val chunk = allBytes.copyOfRange(start, end)

                    client.post("$serverUrl/api/phone/upload/chunk") {
                        setBody(
                            MultiPartFormDataContent(
                                formData {
                                    append("transfer_id", transferId.toString())
                                    append("chunk_index", index.toString())
                                    append("device_token", deviceToken)
                                    append(
                                        "chunk",
                                        chunk,
                                        io.ktor.http.Headers.build {
                                            append(HttpHeaders.ContentType, "application/octet-stream")
                                            append(HttpHeaders.ContentDisposition, "filename=chunk.bin")
                                        }
                                    )
                                }
                            )
                        )
                    }
                    onProgress(index + 1, totalChunks)
                }
            }
        }
    }

    suspend fun downloadJob(serverUrl: String, deviceToken: String, job: JobItem): File {
        val status: DownloadStatusResponse = client.get("$serverUrl/api/phone/download/status/${job.id}") {
            url { parameters.append("device_token", deviceToken) }
        }.body()

        val downloadsDir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS) ?: context.filesDir
        val outputFile = File(downloadsDir, status.filename)

        withContext(Dispatchers.IO) {
            FileOutputStream(outputFile, false).use { out ->
                for (chunkIndex in 0 until status.totalChunks) {
                    val response = client.get("$serverUrl/api/phone/download/chunk/${job.id}/$chunkIndex") {
                        url { parameters.append("device_token", deviceToken) }
                    }
                    val packet = response.bodyAsChannel().readRemaining()
                    out.write(packet.readBytes())
                }
            }
        }

        return outputFile
    }

    fun queryFileName(resolver: ContentResolver, uri: Uri): String? {
        return DocumentFile.fromSingleUri(context, uri)?.name
    }

    fun queryFileSize(resolver: ContentResolver, uri: Uri): Long {
        return DocumentFile.fromSingleUri(context, uri)?.length() ?: 0L
    }
}