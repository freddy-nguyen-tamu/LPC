package com.example.transferapp

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString

private val Context.resumeDataStore by preferencesDataStore(name = "transfer_resume_store")

@Serializable
data class UploadResumeState(
    val transferId: Int,
    val fileUri: String,
    val fileName: String,
    val fileSha256: String,
    val uploadedChunks: List<Int>,
    val totalChunks: Int,
    val chunkSize: Int,
)

class ResumeStore(private val context: Context) {
    private fun key(deviceToken: String, fileName: String) =
        stringPreferencesKey("${deviceToken}::${fileName}")

    suspend fun save(deviceToken: String, fileName: String, state: UploadResumeState) {
        context.resumeDataStore.edit { prefs ->
            prefs[key(deviceToken, fileName)] = NetworkModule.json.encodeToString(state)
        }
    }

    suspend fun load(deviceToken: String, fileName: String): UploadResumeState? {
        val raw = context.resumeDataStore.data.map { it[key(deviceToken, fileName)] }.first() ?: return null
        return runCatching { NetworkModule.json.decodeFromString<UploadResumeState>(raw) }.getOrNull()
    }

    suspend fun clear(deviceToken: String, fileName: String) {
        context.resumeDataStore.edit { prefs ->
            prefs.remove(key(deviceToken, fileName))
        }
    }
}