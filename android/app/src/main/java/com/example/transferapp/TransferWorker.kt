package com.example.transferapp

import android.content.Context
import android.net.Uri
import androidx.core.app.NotificationChannelCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkerParameters

class TransferWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result {
        val serverUrl = inputData.getString("server_url") ?: return Result.failure()
        val deviceToken = inputData.getString("device_token") ?: return Result.failure()
        val fileUri = inputData.getString("file_uri") ?: return Result.failure()

        setForeground(createForegroundInfo("Preparing upload"))
        val repo = TransferRepository(applicationContext)

        return try {
            repo.uploadFileChunked(serverUrl, deviceToken, Uri.parse(fileUri)) { sent, total ->
                setForeground(createForegroundInfo("Uploading $sent / $total chunks"))
            }
            Result.success()
        } catch (_: Exception) {
            Result.retry()
        }
    }

    private fun createForegroundInfo(text: String): ForegroundInfo {
        val channelId = "transfer_uploads"
        val channel = NotificationChannelCompat.Builder(
            channelId,
            NotificationManagerCompat.IMPORTANCE_LOW
        ).setName("Transfer uploads").build()

        NotificationManagerCompat.from(applicationContext).createNotificationChannel(channel)

        val notification = NotificationCompat.Builder(applicationContext, channelId)
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setContentTitle("Transfer Pro")
            .setContentText(text)
            .setOngoing(true)
            .build()

        return ForegroundInfo(101, notification)
    }
}