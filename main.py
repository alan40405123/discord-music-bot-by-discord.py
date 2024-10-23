import discord
from discord import app_commands
import yt_dlp
import asyncio

ytdl_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
}

ffmpeg_options = {
    'options': '-vn',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
}

ytdl = yt_dlp.YoutubeDL(ytdl_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

class ServerState:
    def __init__(self):
        self.voice_channel = None
        self.looping = False
        self.current_song_url = None
        self.queue = []

class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.servers = {}

    async def setup_hook(self):
        await self.tree.sync()

intents = discord.Intents.default()
client = MyClient(intents=intents)

async def play_next_song(guild, server_state):
    """ 播放下一首歌曲 """
    if server_state.looping and server_state.current_song_url:
        player = await YTDLSource.from_url(server_state.current_song_url, stream=True)
        guild.voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next_song(guild, server_state), client.loop))
    elif server_state.queue:
        player = server_state.queue.pop(0)
        server_state.current_song_url = player.url
        guild.voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next_song(guild, server_state), client.loop))

@client.tree.command()
async def join(interaction: discord.Interaction):
    """ 加入語音頻道 """
    if interaction.user.voice:
        server_state = client.servers.setdefault(interaction.guild.id, ServerState())
        if server_state.voice_channel is None:
            server_state.voice_channel = await interaction.user.voice.channel.connect()
            
            await interaction.response.send_message(f"正在加入語音頻道:<#{interaction.user.voice.channel.id}>")
        else:
            await interaction.response.send_message(f"已經在語音頻道<#{interaction.user.voice.channel.id}裡")
    else:
        await interaction.response.send_message("你不在語音頻道裡，請先加入語音頻道")
    
@client.tree.command()
@app_commands.describe(search="音樂的連結網址(也可直接輸入歌曲名稱)")
async def play(interaction: discord.Interaction, search: str):
    """ 播放音樂 """
    if interaction.user.voice:
        server_state = client.servers.setdefault(interaction.guild.id, ServerState())
        if server_state.voice_channel is None:
            server_state.voice_channel = await interaction.user.voice.channel.connect()
            await interaction.response.send_message(f"自動加入語音頻道<#{interaction.user.voice.channel.id}>，將開始播放 {search}")
        else:
            await interaction.response.send_message(f"已將 {search} 加入播放清單")

        try:
            player = await YTDLSource.from_url(search, stream=True)
            server_state.queue.append(player)
            if not server_state.voice_channel.is_playing():
                await play_next_song(interaction.guild, server_state)
        except Exception as e:
            await interaction.response.send_message(f"播放音樂時發生錯誤: {e}")
    else:
        await interaction.response.send_message("你不在語音頻道裡，請先加入語音頻道")

@client.tree.command()
async def skip(interaction: discord.Interaction):
    """ 跳過當前歌曲 """
    server_state = client.servers.get(interaction.guild.id)
    if server_state and server_state.voice_channel:
        if server_state.voice_channel.is_playing():
            server_state.voice_channel.stop()
            await interaction.response.send_message("已跳過當前歌曲。")
            await play_next_song(interaction.guild, server_state)
        else:
            await interaction.response.send_message("目前沒有歌曲在播放。")
    else:
        await interaction.response.send_message("不在語音頻道裡，請先加入。")

@client.tree.command()
async def loop(interaction: discord.Interaction):
    """ 切換循環播放 """
    server_state = client.servers.get(interaction.guild.id)
    if server_state:
        server_state.looping = not server_state.looping
        state = "開啟" if server_state.looping else "關閉"
        await interaction.response.send_message(f"循環播放已{state}。")
    else:
        await interaction.response.send_message("不在語音頻道裡，請先加入。")

@client.tree.command()
async def pause(interaction: discord.Interaction):
    """ 暫停 """
    server_state = client.servers.get(interaction.guild.id)
    if server_state and server_state.voice_channel:
        if server_state.voice_channel.is_playing():
            server_state.voice_channel.pause()
            await interaction.response.send_message("暫停播放")
        else:
            await interaction.response.send_message("音樂已經暫停")
    else:
        await interaction.response.send_message("不在語音頻道裡，請先加入")

@client.tree.command()
async def resume(interaction: discord.Interaction):
    """ 取消暫停 """
    server_state = client.servers.get(interaction.guild.id)
    if server_state and server_state.voice_channel:
        if server_state.voice_channel.is_paused():
            server_state.voice_channel.resume()
            await interaction.response.send_message("繼續播放")
        else:
            await interaction.response.send_message("音樂沒被暫停")
    else:
        await interaction.response.send_message("不在語音頻道裡，請先加入")

@client.tree.command()
async def stop(interaction: discord.Interaction):
    """ 停止播放 """
    server_state = client.servers.get(interaction.guild.id)
    if server_state and server_state.voice_channel:
        if server_state.voice_channel.is_playing() or server_state.voice_channel.is_paused():
            await server_state.voice_channel.disconnect()
            await interaction.response.send_message("已停止播放並退出語音頻道")
      
            server_state.voice_channel = None
            server_state.looping = False
            server_state.queue.clear()
        else:
            await interaction.response.send_message("目前沒有歌曲在播放。")
    else:
        await interaction.response.send_message("不在語音頻道裡，請先加入。")

@client.tree.command()
async def queue(interaction: discord.Interaction):
    """ 查看播放清單 """
    server_state = client.servers.get(interaction.guild.id)
    if server_state and server_state.queue:
        queue_list = "\n".join([f"{i+1}. {song.title}" for i, song in enumerate(server_state.queue)])
        await interaction.response.send_message(f"播放清單:\n{queue_list}")
    else:
        await interaction.response.send_message("播放清單是空的。")

client.run("your token 你的token")
