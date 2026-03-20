package com.example.transferapp

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Upload
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.transferapp.ui.theme.TransferAppTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            TransferAppTheme {
                val vm: PairingViewModel = viewModel()
                val state by vm.uiState.collectAsState()

                val pickFile = rememberLauncherForActivityResult(
                    contract = ActivityResultContracts.GetContent()
                ) { uri: Uri? ->
                    if (uri != null) vm.upload(uri)
                }

                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(innerPadding)
                            .padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(14.dp)
                    ) {
                        item {
                            Text("Transfer Pro Android", style = MaterialTheme.typography.headlineMedium)
                            Text(
                                "Scan the QR on the laptop, then paste the token and server URL below.",
                                style = MaterialTheme.typography.bodyMedium
                            )
                        }

                        item {
                            Card(colors = CardDefaults.cardColors()) {
                                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                    OutlinedTextField(
                                        value = state.serverUrl,
                                        onValueChange = vm::setServerUrl,
                                        label = { Text("Server URL") },
                                        modifier = Modifier.fillMaxWidth(),
                                        placeholder = { Text("http://192.168.1.20:5000") }
                                    )
                                    OutlinedTextField(
                                        value = state.encryptedToken,
                                        onValueChange = vm::setEncryptedToken,
                                        label = { Text("Encrypted Pair Token") },
                                        modifier = Modifier.fillMaxWidth()
                                    )
                                    OutlinedTextField(
                                        value = state.deviceName,
                                        onValueChange = vm::setDeviceName,
                                        label = { Text("Device Name") },
                                        modifier = Modifier.fillMaxWidth()
                                    )
                                    Button(onClick = { vm.pair() }, modifier = Modifier.fillMaxWidth()) {
                                        Text(if (state.isPaired) "Paired" else "Pair Device")
                                    }
                                    Text(state.message)
                                }
                            }
                        }

                        if (state.isPaired) {
                            item {
                                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                    Button(onClick = { pickFile.launch("*/*") }) {
                                        Icon(Icons.Default.Upload, contentDescription = null)
                                        Spacer(modifier = Modifier.height(0.dp))
                                        Text(" Upload File")
                                    }
                                    Button(onClick = { vm.refreshJobs() }) {
                                        Text("Refresh Jobs")
                                    }
                                }
                            }

                            item {
                                Text("Pending downloads", style = MaterialTheme.typography.titleLarge)
                            }

                            items(state.jobs) { job ->
                                Card {
                                    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                        Text(job.filename, style = MaterialTheme.typography.titleMedium)
                                        Text("${job.sizeBytes} bytes • ${job.totalChunks} chunks")
                                        Button(onClick = { vm.download(job) }) {
                                            Icon(Icons.Default.Download, contentDescription = null)
                                            Text(" Download")
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}