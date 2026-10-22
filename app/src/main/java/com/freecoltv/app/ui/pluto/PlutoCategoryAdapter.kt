package com.freecoltv.app.ui.pluto

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import coil.load
import com.freecoltv.app.R
import com.freecoltv.app.data.pluto.PlutoChannel

class PlutoCategoryAdapter(private val onClick: (PlutoChannel) -> Unit) :
    RecyclerView.Adapter<PlutoCategoryAdapter.ViewHolder>() {

    private val items = mutableListOf<PlutoChannel>()

    fun submit(channels: List<PlutoChannel>) {
        items.clear()
        items.addAll(channels)
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

        fun bind(channel: PlutoChannel) {
            name.text = channel.name
            category.text = channel.category
            number.text = "#${channel.number}"
            if (!channel.logoUrl.isNullOrEmpty()) {
                logo.load(channel.logoUrl) { crossfade(true) }
            } else {
                logo.setImageDrawable(null)
            }
            itemView.setOnClickListener { onClick(channel) }
        }
    }
}
