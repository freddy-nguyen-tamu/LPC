package com.example.transferapp

import android.content.Context
import android.net.Uri
import android.os.Environment
import androidx.documentfile.provider.DocumentFile
import io.ktor.client.call.body
import io.ktor.client.request.forms.MultiPartFormDataContent
import io.ktor.client.request.forms.formData
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.contentType
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.util.Base64

class TransferRepository(private val context: Context) {
    private val client = NetworkModule.http
    private val resumeStore = ResumeStore(context)

    suspend fun pair(serverUrl: String, token: String, deviceName: String): PairResponse {
        return client.post("$serverUrl/api/pair") {
            contentType(ContentType.Application.Json)
            setBody(PairRequest(token, deviceName))
        }.body()
    }

    suspend fun fetchJobs(serverUrl: String, deviceToken: String): JobsResponse {
        return client.get("$serverUrl/api/phone/jobs") {
            url { parameters.append("device_token", deviceToken) }
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
        val fileName = DocumentFile.fromSingleUri(context, fileUri)?.name ?: "upload.bin"
        val mime = resolver.getType(fileUri) ?: "application/octet-stream"
        val size = DocumentFile.fromSingleUri(context, fileUri)?.length() ?: 0L
        val fileHash = resolver.openInputStream(fileUri)!!.use { ChecksumUtils.sha256(it) }

        val init = initUpload(
            serverUrl,
            UploadInitRequest(
                deviceToken = deviceToken,
                filename = fileName,
                sizeBytes = size,
                chunkSize = chunkSize,
                mimeType = mime,
                fileSha256 = fileHash,
            )
        )
        require(init.ok && init.transferId != null && init.totalChunks != null)

        val transferId = init.transferId
        val totalChunks = init.totalChunks

        val status: UploadStatusResponse = client.get("$serverUrl/api/phone/upload/status/$transferId") {
            url { parameters.append("device_token", deviceToken) }
        }.body()

        val uploadedSet = status.uploadedChunks.toMutableSet()

        resumeStore.save(
            deviceToken,
            fileName,
            UploadResumeState(
                transferId = transferId,
                fileUri = fileUri.toString(),
                fileName = fileName,
                fileSha256 = fileHash,
                uploadedChunks = uploadedSet.toList(),
                totalChunks = totalChunks,
                chunkSize = chunkSize,
            )
        )

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
                    val chunkHash = ChecksumUtils.sha256(chunk)

                    client.post("$serverUrl/api/phone/upload/chunk") {
                        setBody(
                            MultiPartFormDataContent(
                                formData {
                                    append("transfer_id", transferId.toString())
                                    append("chunk_index", index.toString())
                                    append("device_token", deviceToken)
                                    append("chunk_sha256", chunkHash)
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

                    uploadedSet.add(index)

                    resumeStore.save(
                        deviceToken,
                        fileName,
                        UploadResumeState(
                            transferId = transferId,
                            fileUri = fileUri.toString(),
                            fileName = fileName,
                            fileSha256 = fileHash,
                            uploadedChunks = uploadedSet.toList().sorted(),
                            totalChunks = totalChunks,
                            chunkSize = chunkSize,
                        )
                    )

                    onProgress(index + 1, totalChunks)
                }
            }
        }

        resumeStore.clear(deviceToken, fileName)
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
                    val response: DownloadChunkResponse =
                        client.get("$serverUrl/api/phone/download/chunk/${job.id}/$chunkIndex") {
                            url { parameters.append("device_token", deviceToken) }
                        }.body()

                    val bytes = Base64.getDecoder().decode(response.dataBase64)
                    val actualHash = ChecksumUtils.sha256(bytes)
                    require(actualHash == response.chunkSha256) {
                        "Chunk checksum mismatch at index $chunkIndex"
                    }
                    out.write(bytes)
                }
            }
        }

        if (!status.fileSha256.isNullOrBlank()) {
            require(ChecksumUtils.sha256(outputFile) == status.fileSha256) {
                "Final file checksum mismatch"
            }
        }

        return outputFile
    }
}