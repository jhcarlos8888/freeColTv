package com.freecoltv.app.ui.pluto

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import coil.load
import com.freecoltv.app.R
import com.freecoltv.app.data.pluto.PlutoChannel
import com.freecoltv.app.data.pluto.PlutoMediaItem

class PlutoCategoryAdapter(private val onClick: (Any) -> Unit) :
    RecyclerView.Adapter<PlutoCategoryAdapter.ViewHolder>() {

    private val items = mutableListOf<Any>()

    fun submit(list: List<Any>) {
        items.clear()
        items.addAll(list)
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context).inflate(R.layout.item_pluto, parent, false)
        return ViewHolder(view)
    }

    override fun getItemCount(): Int = items.size

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(items[position])
    }

    inner class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        private val logo = view.findViewById<android.widget.ImageView>(R.id.plutoLogo)
        private val name = view.findViewById<TextView>(R.id.plutoName)
        private val category = view.findViewById<TextView>(R.id.plutoCategory)
        private val number = view.findViewById<TextView>(R.id.plutoNumber)

        fun bind(item: Any) {
            val itemName = when (item) {
                is PlutoChannel -> item.name
                is PlutoMediaItem -> item.name
                else -> "Sin nombre"
            }
            val itemCategory = when (item) {
                is PlutoChannel -> item.category
                is PlutoMediaItem -> item.categories.takeIf { it.isNotEmpty() }?.joinToString(", ") ?: item.genre
                else -> ""
            }
            val itemImageUrl = when (item) {
                is PlutoChannel -> item.logoUrl
                is PlutoMediaItem -> item.posterUrl
                else -> null
            }
            val itemNumber = when (item) {
                is PlutoChannel -> "#${item.number}"
                is PlutoMediaItem -> if (item.kind.name == "EPISODE") "EP. ${item.episodeNumber}" else itemName.take(10)
                else -> ""
            }
            name.text = itemName
            category.text = itemCategory
            number.text = itemNumber
            if (!itemImageUrl.isNullOrEmpty()) {
                logo.load(itemImageUrl) { crossfade(true) }
            } else {
                logo.setImageDrawable(null)
            }
            itemView.setOnClickListener { onClick(item) }
        }
    }
}
