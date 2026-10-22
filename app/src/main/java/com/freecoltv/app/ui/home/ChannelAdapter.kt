package com.freecoltv.app.ui.home

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import coil.load
import com.freecoltv.app.data.model.Channel
import com.freecoltv.app.databinding.ItemChannelBinding

class ChannelAdapter(
    private val onClick: (Channel) -> Unit,
) : RecyclerView.Adapter<ChannelAdapter.ChannelViewHolder>() {

    private val items = mutableListOf<Channel>()

    fun submit(channels: List<Channel>) {
        items.clear()
        items.addAll(channels)
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ChannelViewHolder {
        val binding = ItemChannelBinding.inflate(LayoutInflater.from(parent.context), parent, false)
        return ChannelViewHolder(binding)
    }

    override fun getItemCount(): Int = items.size

    override fun onBindViewHolder(holder: ChannelViewHolder, position: Int) {
        holder.bind(items[position])
    }

    inner class ChannelViewHolder(
        private val binding: ItemChannelBinding,
    ) : RecyclerView.ViewHolder(binding.root) {

        fun bind(channel: Channel) {
            binding.channelNumber.text = "#${channel.number}"
            binding.channelName.text = channel.name
            binding.channelTag.text = channel.tags.orEmpty()

            val logo = channel.logoUrl
            if (logo.isNullOrBlank()) {
                binding.channelLogo.setImageDrawable(null)
            } else {
                binding.channelLogo.load(logo)
            }
            binding.root.setOnClickListener { onClick(channel) }
        }
    }
}
