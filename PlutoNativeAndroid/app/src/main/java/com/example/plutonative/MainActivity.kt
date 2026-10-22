package com.example.plutonative

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.lazy.items as lazyItems
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import com.example.plutonative.data.PlutoChannel
import com.example.plutonative.data.PlutoRepository
import com.example.plutonative.player.PlayerActivity
import kotlinx.coroutines.launch

private val PlutoBackground = Color(0xFF08080F)
private val PlutoSurface = Color(0xFF171725)
private val PlutoAccent = Color(0xFFFFE000)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val repository = PlutoRepository(applicationContext)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme(
                primary = PlutoAccent,
                onPrimary = Color(0xFF161616),
                background = PlutoBackground,
                surface = PlutoSurface,
                onSurface = Color.White
            )) {
                PlutoLiveScreen(repository = repository) { channel, url ->
                    startActivity(Intent(this, PlayerActivity::class.java).apply {
                        putExtra(PlayerActivity.EXTRA_STREAM_URL, url)
                        putExtra(PlayerActivity.EXTRA_TITLE, channel.name)
                    })
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PlutoLiveScreen(
    repository: PlutoRepository,
    onPlay: (PlutoChannel, String) -> Unit
) {
    val scope = rememberCoroutineScope()
    var channels by remember { mutableStateOf<List<PlutoChannel>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var openingId by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var query by remember { mutableStateOf("") }
    var selectedCategory by remember { mutableStateOf("Todos") }

    fun reload() {
        scope.launch {
            loading = true
            error = null
            try {
                channels = repository.fetchLiveChannels(forceRefresh = true)
                selectedCategory = "Todos"
            } catch (exception: Exception) {
                error = exception.message ?: "No se pudo cargar el catálogo."
            } finally {
                loading = false
            }
        }
    }

    LaunchedEffect(Unit) { reload() }

    val categories = remember(channels) {
        listOf("Todos") + channels.map { it.category }.distinct().sortedBy { it.lowercase() }
    }
    val filtered = remember(channels, selectedCategory, query) {
        channels.filter { channel ->
            (selectedCategory == "Todos" || channel.category == selectedCategory) &&
                (query.isBlank() || channel.name.contains(query, true) || channel.category.contains(query, true))
        }
    }

    Surface(modifier = Modifier.fillMaxSize(), color = PlutoBackground) {
        Column(modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 18.dp, bottom = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Box(
                    modifier = Modifier.size(width = 8.dp, height = 32.dp)
                        .clip(RoundedCornerShape(4.dp)).background(PlutoAccent)
                )
                Column(modifier = Modifier.weight(1f)) {
                    Text("PLUTO TV", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Black)
                    Text("Televisión en vivo", style = MaterialTheme.typography.bodyMedium, color = Color.LightGray)
                }
                IconButton(onClick = { reload() }, enabled = !loading) {
                    Icon(Icons.Default.Refresh, contentDescription = "Actualizar catálogo", tint = Color.White)
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(PlutoSurface).padding(horizontal = 12.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(Icons.Default.Search, contentDescription = null, tint = Color.LightGray)
                Spacer(Modifier.size(8.dp))
                BasicTextField(
                    value = query,
                    onValueChange = { query = it },
                    modifier = Modifier.weight(1f),
                    singleLine = true,
                    textStyle = MaterialTheme.typography.bodyLarge.copy(color = Color.White),
                    keyboardOptions = KeyboardOptions.Default,
                    keyboardActions = KeyboardActions.Default,
                    decorationBox = { inner ->
                        Box {
                            if (query.isEmpty()) Text("Buscar canales…", color = Color.Gray)
                            inner()
                        }
                    }
                )
            }

            Spacer(Modifier.height(10.dp))
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(vertical = 2.dp)) {
                lazyItems(categories) { category ->
                    FilterChip(
                        selected = selectedCategory == category,
                        onClick = { selectedCategory = category },
                        label = { Text(category, maxLines = 1) }
                    )
                }
            }

            Text(
                text = if (channels.isEmpty()) "Canales" else "${filtered.size} canales",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(vertical = 8.dp)
            )

            if (loading) {
                Box(Modifier.fillMaxWidth().weight(1f), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = PlutoAccent)
                }
            } else if (error != null && channels.isEmpty()) {
                Column(
                    modifier = Modifier.fillMaxWidth().weight(1f).padding(20.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {
                    Text("No se pudo cargar Pluto TV", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(8.dp))
                    Text(error.orEmpty(), color = Color.LightGray)
                    Spacer(Modifier.height(16.dp))
                    Button(onClick = { reload() }) { Text("Reintentar") }
                    Text(
                        "Este catálogo depende de endpoints no oficiales; puede fallar por región o por cambios del proveedor.",
                        color = Color.Gray,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(top = 16.dp)
                    )
                }
            } else if (filtered.isEmpty()) {
                Box(Modifier.fillMaxWidth().weight(1f), contentAlignment = Alignment.Center) {
                    Text("No hay canales para este filtro.", color = Color.LightGray)
                }
            } else {
                LazyVerticalGrid(
                    columns = GridCells.Adaptive(minSize = 148.dp),
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    contentPadding = PaddingValues(bottom = 24.dp)
                ) {
                    gridItems(filtered, key = { it.id }) { channel ->
                        ChannelCard(
                            channel = channel,
                            opening = openingId == channel.id,
                            onClick = {
                                scope.launch {
                                    openingId = channel.id
                                    error = null
                                    try {
                                        val streamUrl = repository.playbackUrl(channel)
                                        onPlay(channel, streamUrl)
                                    } catch (exception: Exception) {
                                        error = exception.message ?: "No se pudo preparar el stream."
                                    } finally {
                                        openingId = null
                                    }
                                }
                            }
                        )
                    }
                }
            }

            if (!error.isNullOrBlank() && channels.isNotEmpty()) {
                Text(
                    error.orEmpty(),
                    color = Color(0xFFFFC857),
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(vertical = 6.dp)
                )
            }
        }
    }
}

@Composable
private fun ChannelCard(channel: PlutoChannel, opening: Boolean, onClick: () -> Unit) {
    Card(
        onClick = onClick,
        enabled = !opening,
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = PlutoSurface),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(10.dp)) {
            Box(
                modifier = Modifier.fillMaxWidth().height(94.dp).clip(RoundedCornerShape(8.dp)).background(Color(0xFF222235)),
                contentAlignment = Alignment.Center
            ) {
                if (!channel.logoUrl.isNullOrBlank()) {
                    AsyncImage(
                        model = channel.logoUrl,
                        contentDescription = channel.name,
                        modifier = Modifier.fillMaxSize().padding(12.dp),
                        contentScale = ContentScale.Fit
                    )
                } else {
                    Text(channel.name.take(2).uppercase(), color = PlutoAccent, style = MaterialTheme.typography.headlineMedium)
                }
                if (opening) {
                    CircularProgressIndicator(color = PlutoAccent, modifier = Modifier.size(28.dp), strokeWidth = 3.dp)
                }
            }
            Spacer(Modifier.height(9.dp))
            Text(channel.name, maxLines = 2, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(3.dp))
            Text(channel.category, maxLines = 1, overflow = TextOverflow.Ellipsis, color = Color.LightGray, style = MaterialTheme.typography.bodySmall)
            if (channel.description.isNotBlank()) {
                Spacer(Modifier.height(3.dp))
                Text(channel.description, maxLines = 2, overflow = TextOverflow.Ellipsis, color = Color.Gray, style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}
