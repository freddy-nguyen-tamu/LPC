package com.example.transferapp

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.Data
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class PairingViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = TransferRepository(app.applicationContext)
    private val workManager = WorkManager.getInstance(app)

    private val _uiState = MutableStateFlow(PairUiState())
    val uiState: StateFlow<PairUiState> = _uiState.asStateFlow()

    fun setServerUrl(value: String) {
        _uiState.value = _uiState.value.copy(serverUrl = value)
    }

    fun setEncryptedToken(value: String) {
        _uiState.value = _uiState.value.copy(encryptedToken = value)
    }

    fun setDeviceName(value: String) {
        _uiState.value = _uiState.value.copy(deviceName = value)
    }

    fun applyScannedPair(serverUrl: String, encryptedToken: String) {
        _uiState.value = _uiState.value.copy(
            serverUrl = serverUrl,
            encryptedToken = encryptedToken
        )
    }

    fun pair() {
        val state = _uiState.value
        if (state.serverUrl.isBlank() || state.encryptedToken.isBlank()) {
            _uiState.value = state.copy(message = "Server URL and encrypted token are required.")
            return
        }

        viewModelScope.launch {
            try {
                val res = repo.pair(
                    state.serverUrl.trim(),
                    state.encryptedToken.trim(),
                    state.deviceName.trim()
                )
                if (res.ok && res.deviceToken != null) {
                    _uiState.value = _uiState.value.copy(
                        deviceToken = res.deviceToken,
                        isPaired = true,
                        message = res.message ?: "Paired",
                        serverUrl = res.serverUrl ?: state.serverUrl,
                    )
                    refreshJobs()
                } else {
                    _uiState.value = _uiState.value.copy(message = res.error ?: "Pairing failed")
                }
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(message = e.message ?: "Pairing failed")
            }
        }
    }

    fun refreshJobs() {
        val state = _uiState.value
        if (!state.isPaired || state.deviceToken.isBlank()) return

        viewModelScope.launch {
            try {
                val res = repo.fetchJobs(state.serverUrl, state.deviceToken)
                _uiState.value = _uiState.value.copy(
                    jobs = res.jobs,
                    message = if (res.jobs.isEmpty()) "No pending jobs." else "Found ${res.jobs.size} queued downloads."
                )
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(message = e.message ?: "Failed to refresh jobs")
            }
        }
    }

    fun upload(uri: Uri) {
        val state = _uiState.value
        if (!state.isPaired || state.deviceToken.isBlank()) return

        val req = OneTimeWorkRequestBuilder<TransferWorker>()
            .setInputData(
                Data.Builder()
                    .putString("server_url", state.serverUrl)
                    .putString("device_token", state.deviceToken)
                    .putString("file_uri", uri.toString())
                    .build()
            )
            .build()

        workManager.enqueue(req)
        _uiState.value = _uiState.value.copy(message = "Background upload scheduled")
    }

    fun download(job: JobItem) {
        val state = _uiState.value
        if (!state.isPaired || state.deviceToken.isBlank()) return

        viewModelScope.launch {
            try {
                val file = repo.downloadJob(state.serverUrl, state.deviceToken, job)
                _uiState.value = _uiState.value.copy(message = "Downloaded to ${file.absolutePath}")
                refreshJobs()
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(message = e.message ?: "Download failed")
            }
        }
    }
}