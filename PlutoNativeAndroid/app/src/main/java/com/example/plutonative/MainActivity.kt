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
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
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
import com.example.plutonative.data.PlutoMediaItem
import com.example.plutonative.data.PlutoMediaKind
import com.example.plutonative.data.PlutoRepository
import com.example.plutonative.data.PlutoSeason
import com.example.plutonative.player.PlayerActivity
import kotlinx.coroutines.launch

private val PlutoBackground = Color(0xFF08080F)
private val PlutoSurface = Color(0xFF171725)
private val PlutoAccent = Color(0xFFFFE000)

private enum class CatalogTab(val label: String) {
    LIVE("TV en vivo"), MOVIES("Películas"), SERIES("Series")
}

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
                PlutoCatalogScreen(repository = repository) { title, url ->
                    startActivity(Intent(this, PlayerActivity::class.java).apply {
                        putExtra(PlayerActivity.EXTRA_STREAM_URL, url)
                        putExtra(PlayerActivity.EXTRA_TITLE, title)
                    })
                }
            }
        }
    }
}

@Composable
private fun PlutoCatalogScreen(
    repository: PlutoRepository,
    onPlay: (title: String, url: String) -> Unit
) {
    val scope = rememberCoroutineScope()
    var activeTab by remember { mutableStateOf(CatalogTab.LIVE) }
    var channels by remember { mutableStateOf<List<PlutoChannel>>(emptyList()) }
    var vodItems by remember { mutableStateOf<List<PlutoMediaItem>>(emptyList()) }
    var loading by remember { mutableStateOf(false) }
    var openingId by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var query by remember { mutableStateOf("") }
    var selectedCategory by remember { mutableStateOf("Todos") }
    var selectedSeries by remember { mutableStateOf<PlutoMediaItem?>(null) }
    var seasons by remember { mutableStateOf<List<PlutoSeason>>(emptyList()) }
    var selectedSeasonNumber by remember { mutableStateOf<Int?>(null) }

    fun loadCatalog(tab: CatalogTab, forceRefresh: Boolean = false) {
        scope.launch {
            loading = true
            error = null
            try {
                when (tab) {
                    CatalogTab.LIVE -> channels = repository.fetchLiveChannels(forceRefresh)
                    CatalogTab.MOVIES, CatalogTab.SERIES -> vodItems = repository.fetchVodCatalog(forceRefresh)
                }
            } catch (exception: Exception) {
                error = exception.message ?: "No se pudo cargar el catálogo."
            } finally {
                loading = false
            }
        }
    }

    LaunchedEffect(activeTab) {
        selectedCategory = "Todos"
        query = ""
        if (activeTab == CatalogTab.LIVE && channels.isEmpty()) loadCatalog(activeTab)
        if (activeTab != CatalogTab.LIVE && vodItems.isEmpty()) loadCatalog(activeTab)
    }

    val activeVOD = remember(vodItems, activeTab) {
        when (activeTab) {
            CatalogTab.MOVIES -> vodItems.filter { it.kind == PlutoMediaKind.MOVIE }
            CatalogTab.SERIES -> vodItems.filter { it.kind == PlutoMediaKind.SERIES }
            CatalogTab.LIVE -> emptyList()
        }
    }
    val categories = remember(channels, activeVOD, activeTab, selectedSeries, seasons) {
        when {
            selectedSeries != null -> listOf("Temporadas")
            activeTab == CatalogTab.LIVE -> listOf("Todos") + channels.map { it.category }.distinct().sortedBy { it.lowercase() }
            else -> listOf("Todos") + activeVOD.map { it.genre }.distinct().sortedBy { it.lowercase() }
        }
    }
    val filteredChannels = remember(channels, selectedCategory, query) {
        channels.filter { ch ->
            (selectedCategory == "Todos" || ch.category == selectedCategory) &&
                (query.isBlank() || ch.name.contains(query, true) || ch.category.contains(query, true) || ch.description.contains(query, true))
        }
    }
    val filteredVOD = remember(activeVOD, selectedCategory, query) {
        activeVOD.filter { item ->
            (selectedCategory == "Todos" || item.genre == selectedCategory) &&
                (query.isBlank() || item.name.contains(query, true) || item.genre.contains(query, true) || item.description.contains(query, true))
        }
    }
    val selectedSeason = seasons.firstOrNull { it.number == selectedSeasonNumber }

    Surface(modifier = Modifier.fillMaxSize(), color = PlutoBackground) {
        Column(modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 18.dp, bottom = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                if (selectedSeries != null) {
                    IconButton(onClick = {
                        if (selectedSeasonNumber != null) selectedSeasonNumber = null
                        else {
                            selectedSeries = null
                            seasons = emptyList()
                            selectedCategory = "Todos"
                        }
                        error = null
                    }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Volver", tint = Color.White)
                    }
                } else {
                    Box(
                        modifier = Modifier.size(width = 8.dp, height = 32.dp)
                            .clip(RoundedCornerShape(4.dp)).background(PlutoAccent)
                    )
                }
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = selectedSeason?.let { "${selectedSeries?.name} · Temporada ${it.number}" }
                            ?: selectedSeries?.name ?: "PLUTO TV",
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Black,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    Text(
                        text = if (selectedSeries == null) "Canales, películas y series" else "Episodios y temporadas",
                        style = MaterialTheme.typography.bodyMedium,
                        color = Color.LightGray
                    )
                }
                IconButton(onClick = { loadCatalog(activeTab, forceRefresh = true) }, enabled = !loading) {
                    Icon(Icons.Default.Refresh, contentDescription = "Actualizar catálogo", tint = Color.White)
                }
            }

            if (selectedSeries == null) {
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
                                if (query.isEmpty()) Text(
                                    when (activeTab) {
                                        CatalogTab.LIVE -> "Buscar canales…"
                                        CatalogTab.MOVIES -> "Buscar películas…"
                                        CatalogTab.SERIES -> "Buscar series…"
                                    }, color = Color.Gray
                                )
                                inner()
                            }
                        }
                    )
                }
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CatalogTab.entries.forEach { tab ->
                        FilterChip(
                            selected = activeTab == tab,
                            onClick = {
                                activeTab = tab
                                error = null
                            },
                            label = { Text(tab.label, maxLines = 1) }
                        )
                    }
                }
            } else {
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(vertical = 4.dp)) {
                    lazyItems(seasons, key = { it.number }) { season ->
                        FilterChip(
                            selected = selectedSeasonNumber == season.number,
                            onClick = { selectedSeasonNumber = season.number },
                            label = { Text("Temporada ${season.number} · ${season.episodes.size} ep.") }
                        )
                    }
                }
            }

            if (selectedSeries == null) {
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(vertical = 7.dp)) {
                    lazyItems(categories) { category ->
                        FilterChip(
                            selected = selectedCategory == category,
                            onClick = { selectedCategory = category },
                            label = { Text(category, maxLines = 1) }
                        )
                    }
                }
            }

            val currentEpisodes = selectedSeason?.episodes.orEmpty()
            val displayCount = when {
                selectedSeries != null && selectedSeasonNumber != null -> currentEpisodes.size
                selectedSeries != null -> seasons.size
                activeTab == CatalogTab.LIVE -> filteredChannels.size
                else -> filteredVOD.size
            }
            Text(
                text = when {
                    selectedSeries != null && selectedSeasonNumber != null -> "$displayCount episodios"
                    selectedSeries != null -> "$displayCount temporadas"
                    activeTab == CatalogTab.LIVE -> "$displayCount canales"
                    activeTab == CatalogTab.MOVIES -> "$displayCount películas"
                    else -> "$displayCount series"
                },
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(vertical = 8.dp)
            )

            if (loading) {
                Box(Modifier.fillMaxWidth().weight(1f), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = PlutoAccent)
                }
            } else if (!error.isNullOrBlank() && ((activeTab == CatalogTab.LIVE && channels.isEmpty()) || (activeTab != CatalogTab.LIVE && vodItems.isEmpty()))) {
                Column(
                    modifier = Modifier.fillMaxWidth().weight(1f).padding(20.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {
                    Text("No se pudo cargar Pluto TV", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(8.dp))
                    Text(error.orEmpty(), color = Color.LightGray)
                    Spacer(Modifier.height(16.dp))
                    Button(onClick = { loadCatalog(activeTab, forceRefresh = true) }) { Text("Reintentar") }
                    Text(
                        "El catálogo usa endpoints no oficiales y puede cambiar por región o por actualizaciones del proveedor.",
                        color = Color.Gray,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(top = 16.dp)
                    )
                }
            } else if (selectedSeries != null && selectedSeasonNumber == null) {
                LazyVerticalGrid(
                    columns = GridCells.Adaptive(minSize = 148.dp),
                    modifier = Modifier.fillMaxWidth().weight(1f),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    contentPadding = PaddingValues(bottom = 24.dp)
                ) {
                    gridItems(seasons, key = { "season-${it.number}" }) { season ->
                        SimpleCard(
                            title = "Temporada ${season.number}",
                            subtitle = "${season.episodes.size} episodios",
                            imageUrl = selectedSeries?.posterUrl,
                            onClick = { selectedSeasonNumber = season.number }
                        )
                    }
                }
            } else {
                val hasRows = when {
                    selectedSeries != null -> currentEpisodes.isNotEmpty()
                    activeTab == CatalogTab.LIVE -> filteredChannels.isNotEmpty()
                    else -> filteredVOD.isNotEmpty()
                }
                if (!hasRows) {
                    Box(Modifier.fillMaxWidth().weight(1f), contentAlignment = Alignment.Center) {
                        Text(
                            error ?: when {
                                selectedSeries != null -> "Esta temporada no tiene episodios disponibles."
                                else -> "No hay resultados para este filtro."
                            }, color = Color.LightGray
                        )
                    }
                } else {
                    LazyVerticalGrid(
                        columns = GridCells.Adaptive(minSize = 148.dp),
                        modifier = Modifier.fillMaxWidth().weight(1f),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                        contentPadding = PaddingValues(bottom = 24.dp)
                    ) {
                        when {
                            selectedSeries != null -> gridItems(currentEpisodes, key = { it.id }) { episode ->
                                MediaCard(episode, opening = openingId == episode.id) {
                                    scope.launch {
                                        openingId = episode.id
                                        error = null
                                        try { onPlay(episode.name, repository.playbackUrl(episode)) }
                                        catch (ex: Exception) { error = ex.message ?: "No se pudo preparar el episodio." }
                                        finally { openingId = null }
                                    }
                                }
                            }
                            activeTab == CatalogTab.LIVE -> gridItems(filteredChannels, key = { it.id }) { channel ->
                                ChannelCard(channel, opening = openingId == channel.id) {
                                    scope.launch {
                                        openingId = channel.id
                                        error = null
                                        try { onPlay(channel.name, repository.playbackUrl(channel)) }
                                        catch (ex: Exception) { error = ex.message ?: "No se pudo preparar el canal." }
                                        finally { openingId = null }
                                    }
                                }
                            }
                            else -> gridItems(filteredVOD, key = { it.id }) { item ->
                                MediaCard(item, opening = openingId == item.id) {
                                    if (item.kind == PlutoMediaKind.SERIES) {
                                        scope.launch {
                                            loading = true
                                            error = null
                                            try {
                                                selectedSeries = item
                                                seasons = repository.fetchSeriesSeasons(item)
                                                selectedSeasonNumber = if (seasons.size == 1) seasons.first().number else null
                                            } catch (ex: Exception) {
                                                selectedSeries = null
                                                seasons = emptyList()
                                                error = ex.message ?: "No se pudieron cargar las temporadas."
                                            } finally { loading = false }
                                        }
                                    } else {
                                        scope.launch {
                                            openingId = item.id
                                            error = null
                                            try { onPlay(item.name, repository.playbackUrl(item)) }
                                            catch (ex: Exception) { error = ex.message ?: "No se pudo preparar la película." }
                                            finally { openingId = null }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            if (!error.isNullOrBlank() && ((activeTab == CatalogTab.LIVE && channels.isNotEmpty()) || (activeTab != CatalogTab.LIVE && vodItems.isNotEmpty()))) {
                Text(error.orEmpty(), color = Color(0xFFFFC857), style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(vertical = 6.dp))
            }
        }
    }
}

@Composable
private fun ChannelCard(channel: PlutoChannel, opening: Boolean, onClick: () -> Unit) {
    ContentCard(
        title = channel.name,
        subtitle = channel.category + if (channel.description.isNotBlank()) " · ${channel.description}" else "",
        imageUrl = channel.logoUrl,
        badge = if (!channel.number.isNullOrBlank()) "CH ${channel.number}" else "EN VIVO",
        opening = opening,
        onClick = onClick
    )
}

@Composable
private fun MediaCard(item: PlutoMediaItem, opening: Boolean, onClick: () -> Unit) {
    val badge = when (item.kind) {
        PlutoMediaKind.MOVIE -> "PELÍCULA"
        PlutoMediaKind.SERIES -> "SERIE"
        PlutoMediaKind.EPISODE -> item.seasonNumber?.let { "TEMP. $it" } ?: "EPISODIO"
    }
    ContentCard(
        title = item.name,
        subtitle = listOf(item.genre, item.rating, item.description).filter { it.isNotBlank() }.joinToString(" · "),
        imageUrl = item.posterUrl,
        badge = badge,
        opening = opening,
        onClick = onClick
    )
}

@Composable
private fun SimpleCard(title: String, subtitle: String, imageUrl: String?, onClick: () -> Unit) {
    ContentCard(title, subtitle, imageUrl, badge = "SERIE", opening = false, onClick = onClick)
}

@Composable
private fun ContentCard(
    title: String,
    subtitle: String,
    imageUrl: String?,
    badge: String,
    opening: Boolean,
    onClick: () -> Unit
) {
    Card(
        onClick = onClick,
        enabled = !opening,
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = PlutoSurface),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(10.dp)) {
            Box(
                modifier = Modifier.fillMaxWidth().height(100.dp).clip(RoundedCornerShape(8.dp)).background(Color(0xFF222235)),
                contentAlignment = Alignment.Center
            ) {
                if (!imageUrl.isNullOrBlank()) {
                    AsyncImage(
                        model = imageUrl,
                        contentDescription = title,
                        modifier = Modifier.fillMaxSize().padding(6.dp),
                        contentScale = ContentScale.Crop
                    )
                } else {
                    Text(title.take(2).uppercase(), color = PlutoAccent, style = MaterialTheme.typography.headlineMedium)
                }
                Text(
                    badge,
                    color = Color.Black,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier.align(Alignment.BottomStart).padding(5.dp)
                        .clip(RoundedCornerShape(5.dp)).background(PlutoAccent).padding(horizontal = 6.dp, vertical = 3.dp)
                )
                if (opening) CircularProgressIndicator(color = PlutoAccent, modifier = Modifier.size(28.dp), strokeWidth = 3.dp)
            }
            Spacer(Modifier.height(9.dp))
            Text(title, maxLines = 2, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(3.dp))
            Text(subtitle.ifBlank { "Contenido de Pluto TV" }, maxLines = 3, overflow = TextOverflow.Ellipsis, color = Color.LightGray, style = MaterialTheme.typography.bodySmall)
        }
    }
}
