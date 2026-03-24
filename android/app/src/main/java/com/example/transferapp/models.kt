package com.example.transferapp

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class PairRequest(
    @SerialName("encrypted_token") val encryptedToken: String,
    @SerialName("device_name") val deviceName: String,
    val platform: String = "Android"
)

@Serializable
data class PairResponse(
    val ok: Boolean,
    @SerialName("device_id") val deviceId: Int? = null,
    @SerialName("device_token") val deviceToken: String? = null,
    @SerialName("server_url") val serverUrl: String? = null,
    val message: String? = null,
    val error: String? = null
)

@Serializable
data class UploadInitRequest(
    @SerialName("device_token") val deviceToken: String,
    val filename: String,
    @SerialName("size_bytes") val sizeBytes: Long,
    @SerialName("chunk_size") val chunkSize: Int,
    @SerialName("mime_type") val mimeType: String,
    @SerialName("file_sha256") val fileSha256: String
)

@Serializable
data class UploadInitResponse(
    val ok: Boolean,
    @SerialName("transfer_id") val transferId: Int? = null,
    @SerialName("chunk_size") val chunkSize: Int? = null,
    @SerialName("total_chunks") val totalChunks: Int? = null,
    val error: String? = null
)

@Serializable
data class UploadStatusResponse(
    val ok: Boolean,
    @SerialName("uploaded_chunks") val uploadedChunks: List<Int> = emptyList(),
    @SerialName("uploaded_count") val uploadedCount: Int = 0,
    @SerialName("total_chunks") val totalChunks: Int = 0,
    val status: String = "",
    val error: String? = null
)

@Serializable
data class JobItem(
    val id: Int,
    val filename: String,
    @SerialName("mime_type") val mimeType: String,
    @SerialName("size_bytes") val sizeBytes: Long,
    @SerialName("total_chunks") val totalChunks: Int,
    @SerialName("chunk_size") val chunkSize: Int,
    val status: String,
    @SerialName("created_at") val createdAt: String,
    @SerialName("file_sha256") val fileSha256: String? = null
)

@Serializable
data class JobsResponse(
    val ok: Boolean,
    val jobs: List<JobItem> = emptyList(),
    val error: String? = null
)

@Serializable
data class DownloadStatusResponse(
    val ok: Boolean,
    @SerialName("transfer_id") val transferId: Int,
    val filename: String,
    @SerialName("chunk_size") val chunkSize: Int,
    @SerialName("total_chunks") val totalChunks: Int,
    @SerialName("size_bytes") val sizeBytes: Long,
    @SerialName("file_sha256") val fileSha256: String? = null,
    val error: String? = null
)

@Serializable
data class DownloadChunkResponse(
    val ok: Boolean,
    @SerialName("chunk_index") val chunkIndex: Int,
    @SerialName("chunk_sha256") val chunkSha256: String,
    @SerialName("data_base64") val dataBase64: String,
    @SerialName("is_last") val isLast: Boolean
)

data class PairUiState(
    val serverUrl: String = "",
    val encryptedToken: String = "",
    val deviceName: String = "Android Phone",
    val deviceToken: String = "",
    val isPaired: Boolean = false,
    val message: String = "",
    val jobs: List<JobItem> = emptyList()
)