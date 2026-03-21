package com.example.transferapp.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

private val DarkColors = darkColorScheme(
    primary = Cyan,
    secondary = Mint,
    background = DarkNavy,
    surface = PanelBlue,
    onPrimary = DarkNavy,
    onBackground = SoftWhite,
    onSurface = SoftWhite,
)

private val LightColors = lightColorScheme()

@Composable
fun TransferAppTheme(content: @Composable () -> Unit) {
    val colors = if (isSystemInDarkTheme()) DarkColors else LightColors
    MaterialTheme(
        colorScheme = colors,
        typography = Typography,
        content = content,
    )
}