import discord
from discord.ext import commands
from discord.utils import get
import asyncio
from datetime import datetime, timedelta
import json
import os
from flask import Flask
from threading import Thread

app = Flask(__name__)
@app.route('/')
def home(): return "Kross Sentinel - Aktif"
def run_flask(): app.run(host='0.0.0.0', port=8080)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='.', intents=intents, help_command=None)

# -------------------- AYARLAR --------------------
TICKET_KATEGORI = "Destek Talepleri"
DESTEK_KANALI = "🎫・destek"
DESTEK_YETKILI = "Destek Yetkilisi"

BASVURU_KANALI = "📝・başvuru"
BASVURU_LOG = "📋・başvuru-log"
BASVURU_YETKILI = "Başvuru Yetkilisi"

OY_KANALI = "🗳️・oylama"
MOD_LOG = "mod-log"

ONERI_KANALI = "önerim-var"
ONERI_LOG = "öneriler-log"

OZEL_ROLLER = ["CHIEF OF KROSS", "FOUNDER'S ASSISTANT", "FOUNDER-OF-KROSS"]

VERI_DOSYASI = "sentinel_data.json"

# -------------------- VERİ --------------------
def veri_yukle():
    if os.path.exists(VERI_DOSYASI):
        with open(VERI_DOSYASI, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "tickets": {}, "basvurular": [], "oneriler": [], "oneri_sayac": 0,
        "puanlar": {},
        "istatistik": {
            "toplam_ticket": 0, "toplam_basvuru": 0,
            "onaylanan": 0, "reddedilen": 0, "toplam_oneri": 0
        }
    }

def veri_kaydet(veri):
    with open(VERI_DOSYASI, 'w', encoding='utf-8') as f:
        json.dump(veri, f, ensure_ascii=False, indent=2)

def ozel_rol_kontrol(member):
    for rol_adi in OZEL_ROLLER:
        rol = get(member.guild.roles, name=rol_adi)
        if rol and rol in member.roles:
            return True
    return False

async def ticket_kapat(interaction, ticket, puan=None, yorum=None):
    """Ticket'ı kapat, log'a gönder"""
    veri = veri_yukle()
    
    # Transkript kaydet
    messages = []
    async for msg in interaction.channel.history(limit=100, oldest_first=True):
        messages.append(f"[{msg.created_at.strftime('%H:%M')}] {msg.author.name}: {msg.content}")
    transcript = "\n".join(messages)
    
    transcript_dosya = None
    if transcript:
        with open(f"transcript_{interaction.channel.id}.txt", "w", encoding="utf-8") as f:
            f.write(transcript)
        transcript_dosya = discord.File(f"transcript_{interaction.channel.id}.txt")
    
    # Süre hesapla
    acilis = datetime.fromisoformat(ticket["acilis"])
    kapanis = datetime.now()
    sure = kapanis - acilis
    if sure.seconds >= 3600:
        sure_str = f"{sure.seconds // 3600}s { (sure.seconds % 3600) // 60 }dk"
    else:
        sure_str = f"{sure.seconds // 60}dk {sure.seconds % 60}sn"
    
    # Ticket sahibi
    sahip = interaction.guild.get_member(ticket["sahip"])
    sahip_adi = sahip.mention if sahip else f"ID: {ticket['sahip']}"
    
    # İlgilenen yetkili
    alan_adi = "❌ Alınmadı"
    if ticket["alan"]:
        alan = interaction.guild.get_member(ticket["alan"])
        alan_adi = alan.mention if alan else f"ID: {ticket['alan']}"
    
    # Log embed'i
    log_embed = discord.Embed(
        title="🔒 TICKET KAPATILDI",
        color=0xFF0000,
        timestamp=datetime.now()
    )
    log_embed.add_field(name="📋 Kanal", value=f"`{interaction.channel.name}`", inline=True)
    log_embed.add_field(name="👤 Açan", value=sahip_adi, inline=True)
    log_embed.add_field(name="🤝 İlgilenen", value=alan_adi, inline=True)
    log_embed.add_field(name="📅 Açılış", value=f"<t:{int(acilis.timestamp())}:F>", inline=True)
    log_embed.add_field(name="🔒 Kapanış", value=f"<t:{int(kapanis.timestamp())}:F>", inline=True)
    log_embed.add_field(name="⏱️ Süre", value=f"**{sure_str}**", inline=True)
    log_embed.add_field(name="🔒 Kapatan", value=interaction.user.mention, inline=True)
    
    if puan:
        yildizlar = "⭐" * puan + "☆" * (5 - puan)
        log_embed.add_field(name="⭐ Puan", value=f"**{puan}/5** {yildizlar}", inline=True)
        if yorum:
            log_embed.add_field(name="💬 Yorum", value=yorum[:100], inline=True)
    
    log_embed.set_footer(text=f"Ticket ID: {interaction.channel.id}")
    
    # Log kanalına gönder
    log_kanal = get(interaction.guild.text_channels, name=MOD_LOG)
    if log_kanal:
        await log_kanal.send(embed=log_embed)
        if transcript_dosya:
            await log_kanal.send(file=transcript_dosya)
    
    # Dosyayı temizle
    if os.path.exists(f"transcript_{interaction.channel.id}.txt"):
        os.remove(f"transcript_{interaction.channel.id}.txt")
    
    # Ticket'ı veriden sil
    if str(interaction.channel.id) in veri["tickets"]:
        del veri["tickets"][str(interaction.channel.id)]
    veri_kaydet(veri)
    
    # Kanalı sil
    try: await interaction.channel.delete()
    except: pass

# -------------------- ÖNERİ SİSTEMİ --------------------
class OneriButon(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="💡 Öneri Gönder", style=discord.ButtonStyle.green, custom_id="oneri_gonder", emoji="💡")
    async def oneri_gonder(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(OneriModal())

class OneriModal(discord.ui.Modal, title="💡 Öneri Formu"):
    oneri = discord.ui.TextInput(label="Öneriniz Nedir?", placeholder="Sadece bir öneri yazın...", required=True, style=discord.TextStyle.paragraph, max_length=1000)
    
    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild; member = interaction.user
        log_kanal = get(guild.text_channels, name=ONERI_LOG)
        if not log_kanal: return await interaction.response.send_message("❌ `öneriler-log` kanalı bulunamadı!", ephemeral=True)
        
        veri = veri_yukle(); oneri_no = veri.get("oneri_sayac", 0) + 1
        veri["oneri_sayac"] = oneri_no
        veri["oneriler"].append({"no": oneri_no, "kullanici_id": member.id, "kullanici_adi": member.name, "oneri": self.oneri.value, "tarih": datetime.now().isoformat(), "durum": "bekliyor", "yorum": None})
        veri["istatistik"]["toplam_oneri"] = len(veri["oneriler"]); veri_kaydet(veri)
        
        embed = discord.Embed(title=f"💡 Yeni Öneri #{oneri_no}", description=self.oneri.value, color=0xFFD700, timestamp=datetime.now())
        embed.add_field(name="👤 Gönderen", value=f"{member.mention} ({member.name})", inline=True)
        embed.add_field(name="📊 Durum", value="⏳ Beklemede", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url); embed.set_footer(text="Kross Öneri Sistemi")
        
        await log_kanal.send(embed=embed, view=OneriDegerlendir(oneri_no))
        try: await member.send(embed=discord.Embed(title="💡 Öneriniz Alındı!", description=f"**{guild.name}** sunucusuna öneriniz iletildi.", color=0xFFD700).add_field(name="📋 Öneri No", value=f"#{oneri_no}").set_footer(text="Sonuç DM ile bildirilecek"))
        except: pass
        await interaction.response.send_message("✅ Öneriniz gönderildi!", ephemeral=True)

class OneriDegerlendir(discord.ui.View):
    def __init__(self, oneri_no):
        super().__init__(timeout=None); self.oneri_no = oneri_no
    
    @discord.ui.button(label="✅ Onayla", style=discord.ButtonStyle.green, custom_id="oneri_onay")
    async def onayla(self, interaction: discord.Interaction, button: discord.ui.Button):
        veri = veri_yukle(); kullanici_id = None
        for o in veri["oneriler"]:
            if o["no"] == self.oneri_no: o["durum"] = "onaylandı"; kullanici_id = o["kullanici_id"]; break
        veri_kaydet(veri)
        if kullanici_id:
            try:
                user = await bot.fetch_user(int(kullanici_id))
                await user.send(embed=discord.Embed(title="✅ Öneriniz Onaylandı!", description=f"**{interaction.guild.name}** | **#{self.oneri_no}** onaylandı!", color=0x00FF00).add_field(name="🌟 Teşekkürler!", value="Sizin gibi düşünen üyelerimiz olduğu için çok şanslıyız!").add_field(name="💫 İyi Eğlenceler!", value="Kross Ailesi olarak keyifli vakitler dileriz!"))
            except: pass
        button.disabled = True; self.children[1].disabled = True; self.children[2].disabled = True
        await interaction.message.edit(view=self); await interaction.response.send_message(f"✅ #{self.oneri_no} onaylandı!")
    
    @discord.ui.button(label="❌ Reddet", style=discord.ButtonStyle.red, custom_id="oneri_red")
    async def reddet(self, interaction: discord.Interaction, button: discord.ui.Button):
        veri = veri_yukle(); kullanici_id = None
        for o in veri["oneriler"]:
            if o["no"] == self.oneri_no: o["durum"] = "reddedildi"; kullanici_id = o["kullanici_id"]; break
        veri_kaydet(veri)
        if kullanici_id:
            try:
                user = await bot.fetch_user(int(kullanici_id))
                await user.send(embed=discord.Embed(title="❌ Öneriniz Reddedildi", description=f"**{interaction.guild.name}** | **#{self.oneri_no}** şu an için uygun görülmedi.", color=0xFF0000).add_field(name="💭 Üzülmeyin!", value="Başka önerilerinizi bekliyoruz!").add_field(name="💫 İyi Eğlenceler!", value="Kross Ailesi olarak keyifli vakitler dileriz!"))
            except: pass
        button.disabled = True; self.children[0].disabled = True; self.children[2].disabled = True
        await interaction.message.edit(view=self); await interaction.response.send_message(f"❌ #{self.oneri_no} reddedildi!")
    
    @discord.ui.button(label="💬 Yorum", style=discord.ButtonStyle.grey, custom_id="oneri_yorum")
    async def yorum(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(OneriYorumModal(self.oneri_no))

class OneriYorumModal(discord.ui.Modal, title="💬 Öneri Yorumu"):
    yorum = discord.ui.TextInput(label="Yorumunuz", placeholder="Öneri hakkında yorum...", required=True, style=discord.TextStyle.paragraph, max_length=500)
    def __init__(self, oneri_no): super().__init__(); self.oneri_no = oneri_no
    async def on_submit(self, interaction: discord.Interaction):
        veri = veri_yukle(); kullanici_id = None
        for o in veri["oneriler"]:
            if o["no"] == self.oneri_no: o["yorum"] = self.yorum.value; kullanici_id = o["kullanici_id"]; break
        veri_kaydet(veri)
        if kullanici_id:
            try:
                user = await bot.fetch_user(int(kullanici_id))
                await user.send(embed=discord.Embed(title="💬 Önerinize Yorum Geldi!", description=f"**{interaction.guild.name}** | **#{self.oneri_no}**", color=0x5865F2).add_field(name="💭 Yetkili Yorumu", value=self.yorum.value))
            except: pass
        await interaction.response.send_message("✅ Yorum gönderildi!", ephemeral=True)

# -------------------- TİCKET SİSTEMİ --------------------
class PuanModal(discord.ui.Modal, title="⭐ Yetkiliyi Puanla"):
    puan = discord.ui.TextInput(label="Puan (1-5)", placeholder="1-5 arası yıldız ver...", required=True, max_length=1)
    yorum = discord.ui.TextInput(label="Yorum (opsiyonel)", placeholder="Yetkili hakkında yorum...", required=False, style=discord.TextStyle.paragraph, max_length=200)
    
    def __init__(self, yetkili_id, yetkili_adi, ticket_id, original_interaction):
        super().__init__()
        self.yetkili_id = yetkili_id; self.yetkili_adi = yetkili_adi
        self.ticket_id = ticket_id; self.original_interaction = original_interaction
    
    async def on_submit(self, interaction: discord.Interaction):
        if not self.puan.value.isdigit() or not (1 <= int(self.puan.value) <= 5):
            return await interaction.response.send_message("❌ 1-5 arası bir sayı gir!", ephemeral=True)
        
        puan = int(self.puan.value); veri = veri_yukle()
        if "puanlar" not in veri: veri["puanlar"] = {}
        if str(self.yetkili_id) not in veri["puanlar"]:
            veri["puanlar"][str(self.yetkili_id)] = {"isim": self.yetkili_adi, "toplam": 0, "sayi": 0, "yorumlar": []}
        
        veri["puanlar"][str(self.yetkili_id)]["toplam"] += puan
        veri["puanlar"][str(self.yetkili_id)]["sayi"] += 1
        if self.yorum.value:
            veri["puanlar"][str(self.yetkili_id)]["yorumlar"].append({"puan": puan, "yorum": self.yorum.value, "tarih": datetime.now().isoformat()})
        veri_kaydet(veri)
        
        # Ticket'ı kapat
        ticket = veri["tickets"].get(self.ticket_id)
        if ticket:
            await ticket_kapat(self.original_interaction, ticket, puan, self.yorum.value)
        else:
            await interaction.response.send_message("✅ Puanlama yapıldı! Ticket kapatıldı.", ephemeral=True)

class TicketKontrol(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    @discord.ui.button(label="📩 Talebi Aç", style=discord.ButtonStyle.green, custom_id="ticket_create", emoji="📩")
    async def ticket_create(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild; member = interaction.user
        kategori = get(guild.categories, name=TICKET_KATEGORI)
        if not kategori:
            try: kategori = await guild.create_category(TICKET_KATEGORI)
            except: return await interaction.response.send_message("❌ Kategori hatası!", ephemeral=True)
        
        for ch in guild.text_channels:
            if ch.name == f"🎫・{member.name.lower().replace(' ', '-')}":
                return await interaction.response.send_message(f"❌ Zaten açık: {ch.mention}", ephemeral=True)
        
        yetkili_rol = get(guild.roles, name=DESTEK_YETKILI)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        if yetkili_rol: overwrites[yetkili_rol] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        for rol_adi in OZEL_ROLLER:
            ozel_rol = get(guild.roles, name=rol_adi)
            if ozel_rol: overwrites[ozel_rol] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        kanal = await guild.create_text_channel(f"🎫・{member.name.lower().replace(' ', '-')}", category=kategori, topic=f"Ticket sahibi: {member.id} | Alan: Yok", overwrites=overwrites)
        
        embed = discord.Embed(title="📩 DESTEK TALEBİ", description=f"**{member.mention}** bir destek talebi açtı!\n\n⏰ <t:{int(datetime.now().timestamp())}:R>\n👤 {member.mention}\n🤝 **Alan:** Henüz alınmadı\n\n`.ekle` / `.cikar` / `.kaydet`", color=0x00FF00, timestamp=datetime.now())
        embed.set_footer(text=f"Ticket ID: {kanal.id}")
        
        await kanal.send(embed=embed, view=TicketYonetim(member))
        await kanal.send(f"{member.mention} hoş geldin! {yetkili_rol.mention if yetkili_rol else ''}")
        
        veri = veri_yukle()
        veri["tickets"][str(kanal.id)] = {"sahip": member.id, "alan": None, "acilis": datetime.now().isoformat(), "durum": "açık"}
        veri["istatistik"]["toplam_ticket"] += 1; veri_kaydet(veri)
        await interaction.response.send_message(f"✅ Talep açıldı: {kanal.mention}", ephemeral=True)

class TicketYonetim(discord.ui.View):
    def __init__(self, sahip):
        super().__init__(timeout=None); self.sahip = sahip
    
    @discord.ui.button(label="🤝 Ticketi Al", style=discord.ButtonStyle.blurple, custom_id="ticket_al_btn", emoji="🤝")
    async def ticket_al(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith("🎫・"): return await interaction.response.send_message("❌ Ticket kanalı değil!", ephemeral=True)
        veri = veri_yukle(); ticket = veri["tickets"].get(str(interaction.channel.id))
        if not ticket: return await interaction.response.send_message("❌ Ticket bulunamadı!", ephemeral=True)
        if ticket["alan"] is not None: return await interaction.response.send_message(f"❌ Bu ticket zaten <@{ticket['alan']}> tarafından alınmış!", ephemeral=True)
        
        yetkili_rol = get(interaction.guild.roles, name=DESTEK_YETKILI)
        is_yetkili = yetkili_rol and yetkili_rol in interaction.user.roles
        is_ozel = ozel_rol_kontrol(interaction.user)
        if not is_yetkili and not is_ozel: return await interaction.response.send_message("❌ Yetkin yok!", ephemeral=True)
        
        ticket["alan"] = interaction.user.id; veri_kaydet(veri)
        if yetkili_rol:
            for member in yetkili_rol.members:
                if member.id != interaction.user.id and not ozel_rol_kontrol(member):
                    await interaction.channel.set_permissions(member, send_messages=False)
        
        await interaction.channel.edit(topic=f"Ticket sahibi: {ticket['sahip']} | Alan: {interaction.user.id}")
        await interaction.response.send_message(embed=discord.Embed(title="🤝 Ticket Alındı", description=f"**{interaction.user.mention}** bu ticketi aldı!", color=0x5865F2).set_footer(text="↩️ Vazgeç ile bırakabilirsin"))
    
    @discord.ui.button(label="↩️ Vazgeç", style=discord.ButtonStyle.grey, custom_id="ticket_vazgec_btn", emoji="↩️")
    async def ticket_vazgec(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith("🎫・"): return await interaction.response.send_message("❌ Ticket kanalı değil!", ephemeral=True)
        veri = veri_yukle(); ticket = veri["tickets"].get(str(interaction.channel.id))
        if not ticket: return await interaction.response.send_message("❌ Ticket bulunamadı!", ephemeral=True)
        if ticket["alan"] != interaction.user.id: return await interaction.response.send_message("❌ Bu ticketi sen almamışsın!", ephemeral=True)
        
        ticket["alan"] = None; veri_kaydet(veri)
        yetkili_rol = get(interaction.guild.roles, name=DESTEK_YETKILI)
        if yetkili_rol:
            for member in yetkili_rol.members: await interaction.channel.set_permissions(member, send_messages=True)
        
        await interaction.channel.edit(topic=f"Ticket sahibi: {ticket['sahip']} | Alan: Yok")
        await interaction.response.send_message(embed=discord.Embed(title="↩️ Vazgeçildi", description=f"**{interaction.user.mention}** vazgeçti. Başka yetkili alabilir!", color=0xFFA500))
    
    @discord.ui.button(label="⭐ Puanla & Kapat", style=discord.ButtonStyle.red, custom_id="ticket_close_btn", emoji="⭐")
    async def ticket_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith("🎫・"): return await interaction.response.send_message("❌ Ticket kanalı değil!", ephemeral=True)
        
        veri = veri_yukle(); ticket = veri["tickets"].get(str(interaction.channel.id))
        is_ozel = ozel_rol_kontrol(interaction.user)
        is_sahip = ticket and ticket["sahip"] == interaction.user.id
        
        if ticket and ticket["alan"] != interaction.user.id and not is_ozel and not is_sahip:
            return await interaction.response.send_message("❌ Bu ticketi kapatmaya yetkin yok!", ephemeral=True)
        
        # Ticket sahibi puanlama yapabilir (eğer ticketi alan biri varsa)
        if ticket and is_sahip and ticket["alan"] and ticket["alan"] != interaction.user.id:
            try:
                yetkili = await bot.fetch_user(ticket["alan"])
                modal = PuanModal(ticket["alan"], yetkili.name, str(interaction.channel.id), interaction)
                return await interaction.response.send_modal(modal)
            except: pass
        
        # Puanlama yoksa direkt kapat
        await ticket_kapat(interaction, ticket)
    
    @discord.ui.button(label="📄 Kaydet", style=discord.ButtonStyle.grey, custom_id="ticket_save_btn", emoji="📄")
    async def ticket_save(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith("🎫・"): return await interaction.response.send_message("❌ Ticket kanalı değil!", ephemeral=True)
        messages = []
        async for msg in interaction.channel.history(limit=100, oldest_first=True):
            messages.append(f"[{msg.created_at.strftime('%H:%M')}] {msg.author.name}: {msg.content}")
        transcript = "\n".join(messages)
        log_kanal = get(interaction.guild.text_channels, name=MOD_LOG)
        if log_kanal and transcript:
            with open(f"transcript_{interaction.channel.id}.txt", "w", encoding="utf-8") as f: f.write(transcript)
            await log_kanal.send(f"📄 Transkript - {interaction.channel.name}", file=discord.File(f"transcript_{interaction.channel.id}.txt"))
            os.remove(f"transcript_{interaction.channel.id}.txt")
        await interaction.response.send_message("✅ Transkript kaydedildi!", ephemeral=True)

@bot.command(name='ekle')
@commands.has_permissions(manage_channels=True)
async def ticket_ekle(ctx, member: discord.Member):
    if not ctx.channel.name.startswith("🎫・"): return await ctx.send("❌ Ticket kanalı değil!")
    veri = veri_yukle(); ticket = veri["tickets"].get(str(ctx.channel.id))
    is_ozel = ozel_rol_kontrol(ctx.author)
    if ticket and ticket["alan"] != ctx.author.id and not is_ozel: return await ctx.send("❌ Bu ticketi sen almadın!")
    await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
    await ctx.send(f"✅ {member.mention} talebe eklendi!")

@bot.command(name='cikar')
@commands.has_permissions(manage_channels=True)
async def ticket_cikar(ctx, member: discord.Member):
    if not ctx.channel.name.startswith("🎫・"): return await ctx.send("❌ Ticket kanalı değil!")
    veri = veri_yukle(); ticket = veri["tickets"].get(str(ctx.channel.id))
    is_ozel = ozel_rol_kontrol(ctx.author)
    if ticket and ticket["alan"] != ctx.author.id and not is_ozel: return await ctx.send("❌ Bu ticketi sen almadın!")
    await ctx.channel.set_permissions(member, overwrite=None)
    await ctx.send(f"✅ {member.mention} talepden çıkarıldı!")

@bot.command(name='kaydet')
async def ticket_kaydet(ctx):
    if not ctx.channel.name.startswith("🎫・"): return await ctx.send("❌ Ticket kanalı değil!")
    messages = []
    async for msg in ctx.channel.history(limit=100, oldest_first=True):
        messages.append(f"[{msg.created_at.strftime('%H:%M')}] {msg.author.name}: {msg.content}")
    transcript = "\n".join(messages)
    log_kanal = get(ctx.guild.text_channels, name=MOD_LOG)
    if log_kanal and transcript:
        with open(f"transcript_{ctx.channel.id}.txt", "w", encoding="utf-8") as f: f.write(transcript)
        await log_kanal.send(f"📄 Transkript - {ctx.channel.name}", file=discord.File(f"transcript_{ctx.channel.id}.txt"))
        os.remove(f"transcript_{ctx.channel.id}.txt")
    await ctx.send("✅ Kaydedildi!")

@bot.command(name='puanlar')
async def puanlar(ctx, member: discord.Member = None):
    if member is None: member = ctx.author
    veri = veri_yukle(); puan_data = veri.get("puanlar", {}).get(str(member.id))
    if not puan_data or puan_data["sayi"] == 0: return await ctx.send(f"❌ {member.mention} henüz puanlanmamış!")
    
    ortalama = puan_data["toplam"] / puan_data["sayi"]
    yildizlar = "⭐" * round(ortalama) + "☆" * (5 - round(ortalama))
    
    embed = discord.Embed(title=f"⭐ {member.display_name} Puanları", color=0xFFD700)
    embed.add_field(name="📊 Ortalama", value=f"**{ortalama:.1f}/5** {yildizlar}", inline=False)
    embed.add_field(name="📝 Toplam Oy", value=str(puan_data["sayi"]), inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    if puan_data["yorumlar"]:
        yorumlar = "\n".join([f"⭐{y['puan']} - {y['yorum'][:50]}" for y in puan_data["yorumlar"][-3:]])
        embed.add_field(name="💬 Son Yorumlar", value=yorumlar or "Yok", inline=False)
    await ctx.send(embed=embed)

# -------------------- BAŞVURU SİSTEMİ --------------------
class BasvuruButon(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="📝 Yetkili Başvurusu", style=discord.ButtonStyle.blurple, custom_id="basvuru_btn", emoji="📝")
    async def basvuru_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BasvuruModal())

class BasvuruModal(discord.ui.Modal, title="📝 YETKİLİ BAŞVURU FORMU"):
    isim = discord.ui.TextInput(label="Gerçek Adın", placeholder="Adını yaz", required=True)
    yas = discord.ui.TextInput(label="Yaşın", placeholder="Örn: 18", required=True, max_length=2)
    tecrube = discord.ui.TextInput(label="Daha önce yetkili oldun mu?", placeholder="Hangi sunucularda yetkiliydin?", required=True, style=discord.TextStyle.paragraph)
    neden = discord.ui.TextInput(label="Neden yetkili olmak istiyorsun?", placeholder="Kendini ve hedeflerini anlat", required=True, style=discord.TextStyle.paragraph)
    sure = discord.ui.TextInput(label="Günde kaç saat aktifsin?", placeholder="Örn: 5-6 saat", required=True, max_length=20)
    
    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        log_kanal = get(guild.text_channels, name=BASVURU_LOG)
        if not log_kanal: return await interaction.response.send_message("❌ Başvuru log kanalı yok!", ephemeral=True)
        
        veri = veri_yukle(); basvuru_no = len(veri["basvurular"]) + 1
        embed = discord.Embed(title=f"📝 YENİ BAŞVURU #{basvuru_no}", color=0x5865F2, timestamp=datetime.now())
        embed.add_field(name="👤 Başvuran", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
        embed.add_field(name="📛 Ad", value=self.isim.value, inline=True)
        embed.add_field(name="🎂 Yaş", value=self.yas.value, inline=True)
        embed.add_field(name="⏱️ Aktiflik", value=self.sure.value, inline=True)
        embed.add_field(name="📜 Tecrübe", value=self.tecrube.value, inline=False)
        embed.add_field(name="❓ Neden", value=self.neden.value, inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url); embed.set_footer(text="Kross Sentinel • Başvuru")
        
        veri["basvurular"].append({"no": basvuru_no, "kullanici_id": interaction.user.id, "isim": self.isim.value, "yas": self.yas.value, "tecrube": self.tecrube.value, "neden": self.neden.value, "sure": self.sure.value, "durum": "bekliyor", "tarih": datetime.now().isoformat()})
        veri["istatistik"]["toplam_basvuru"] += 1; veri_kaydet(veri)
        
        yetkili_rol = get(guild.roles, name=BASVURU_YETKILI)
        await log_kanal.send(f"{yetkili_rol.mention if yetkili_rol else ''} Yeni başvuru!", embed=embed, view=BasvuruDegerlendir(interaction.user, basvuru_no))
        try: await interaction.user.send(f"✅ **{guild.name}** başvurun alındı! (#{basvuru_no})")
        except: pass
        await interaction.response.send_message("✅ Başvurun alındı!", ephemeral=True)

class BasvuruDegerlendir(discord.ui.View):
    def __init__(self, basvuran, basvuru_no):
        super().__init__(timeout=None); self.basvuran = basvuran; self.basvuru_no = basvuru_no
    
    @discord.ui.button(label="✅ Onayla", style=discord.ButtonStyle.green, custom_id="basvuru_onayla")
    async def onayla(self, interaction: discord.Interaction, button: discord.ui.Button):
        veri = veri_yukle()
        for b in veri["basvurular"]:
            if b["no"] == self.basvuru_no: b["durum"] = "onaylandı"; break
        veri["istatistik"]["onaylanan"] += 1; veri_kaydet(veri)
        try: await self.basvuran.send(f"🎉 **{interaction.guild.name}** başvurun **ONAYLANDI!**")
        except: pass
        button.disabled = True; self.children[1].disabled = True; self.children[2].disabled = True; self.children[3].disabled = True
        await interaction.message.edit(view=self); await interaction.response.send_message(f"✅ #{self.basvuru_no} onaylandı!")
    
    @discord.ui.button(label="❌ Reddet", style=discord.ButtonStyle.red, custom_id="basvuru_reddet")
    async def reddet(self, interaction: discord.Interaction, button: discord.ui.Button):
        veri = veri_yukle()
        for b in veri["basvurular"]:
            if b["no"] == self.basvuru_no: b["durum"] = "reddedildi"; break
        veri["istatistik"]["reddedilen"] += 1; veri_kaydet(veri)
        try: await self.basvuran.send(f"❌ **{interaction.guild.name}** başvurun **REDDEDİLDİ.**")
        except: pass
        button.disabled = True; self.children[0].disabled = True; self.children[2].disabled = True; self.children[3].disabled = True
        await interaction.message.edit(view=self); await interaction.response.send_message(f"❌ #{self.basvuru_no} reddedildi!")
    
    @discord.ui.button(label="💬 Yorum", style=discord.ButtonStyle.grey, custom_id="basvuru_yorum")
    async def yorum(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(YorumModal(self.basvuran, self.basvuru_no))
    
    @discord.ui.button(label="🔄 Yeniden Değerlendir", style=discord.ButtonStyle.blurple, custom_id="basvuru_yeniden", emoji="🔄")
    async def yeniden_degerlendir(self, interaction: discord.Interaction, button: discord.ui.Button):
        veri = veri_yukle()
        for b in veri["basvurular"]:
            if b["no"] == self.basvuru_no: b["durum"] = "bekliyor"; break
        veri["istatistik"]["onaylanan"] = sum(1 for b in veri["basvurular"] if b["durum"] == "onaylandı")
        veri["istatistik"]["reddedilen"] = sum(1 for b in veri["basvurular"] if b["durum"] == "reddedildi")
        veri_kaydet(veri)
        self.children[0].disabled = False; self.children[1].disabled = False; self.children[2].disabled = False; self.children[3].disabled = True
        await interaction.message.edit(view=self)
        try: await self.basvuran.send(f"🔄 **{interaction.guild.name}** | #{self.basvuru_no} başvurun **yeniden değerlendirmeye** alındı!")
        except: pass
        await interaction.response.send_message(f"🔄 #{self.basvuru_no} yeniden değerlendirmeye alındı!")

class YorumModal(discord.ui.Modal, title="💬 Başvuru Yorumu"):
    yorum = discord.ui.TextInput(label="Yorumun", placeholder="Başvuru hakkında yorum...", required=True, style=discord.TextStyle.paragraph)
    def __init__(self, basvuran, basvuru_no): super().__init__(); self.basvuran = basvuran; self.basvuru_no = basvuru_no
    async def on_submit(self, interaction: discord.Interaction):
        try: await self.basvuran.send(f"💬 #{self.basvuru_no}:\n{self.yorum.value}")
        except: pass
        await interaction.response.send_message("✅ Yorum gönderildi!", ephemeral=True)

# -------------------- OYLAMA --------------------
@bot.command(name='oylama')
@commands.has_permissions(manage_messages=True)
async def oylama(ctx, sure: int = 0, *, soru: str):
    await ctx.message.delete()
    embed = discord.Embed(title="🗳️ OYLAMA", description=soru, color=0x5865F2, timestamp=datetime.now())
    embed.add_field(name="⏱️ Süre", value=f"{sure} dk" if sure > 0 else "Süresiz", inline=True)
    embed.add_field(name="👤 Açan", value=ctx.author.mention, inline=True)
    embed.set_footer(text="✅ Evet • ❌ Hayır • 🤷 Çekimser")
    msg = await ctx.send("@everyone", embed=embed)
    await msg.add_reaction("✅"); await msg.add_reaction("❌"); await msg.add_reaction("🤷")
    if sure > 0:
        await asyncio.sleep(sure * 60)
        msg = await ctx.channel.fetch_message(msg.id)
        evet = hayir = cekimser = 0
        for r in msg.reactions:
            if str(r.emoji) == "✅": evet = r.count - 1
            elif str(r.emoji) == "❌": hayir = r.count - 1
            elif str(r.emoji) == "🤷": cekimser = r.count - 1
        sonuc = discord.Embed(title="🗳️ SONUÇ", description=soru, color=0x00FF00 if evet > hayir else 0xFF0000)
        sonuc.add_field(name="✅ Evet", value=str(evet), inline=True)
        sonuc.add_field(name="❌ Hayır", value=str(hayir), inline=True)
        sonuc.add_field(name="🤷 Çekimser", value=str(cekimser), inline=True)
        await ctx.send(embed=sonuc)

# -------------------- İSTATİSTİK --------------------
@bot.command(name='istatistik')
@commands.has_permissions(manage_messages=True)
async def istatistik(ctx):
    veri = veri_yukle(); ist = veri["istatistik"]
    embed = discord.Embed(title="📊 SENTINEL İSTATİSTİK", color=0x5865F2, timestamp=datetime.now())
    embed.add_field(name="📩 Ticket", value=str(ist["toplam_ticket"]), inline=True)
    embed.add_field(name="📝 Başvuru", value=str(ist["toplam_basvuru"]), inline=True)
    embed.add_field(name="💡 Öneri", value=str(ist["toplam_oneri"]), inline=True)
    embed.add_field(name="✅ Onaylanan", value=str(ist["onaylanan"]), inline=True)
    embed.add_field(name="❌ Reddedilen", value=str(ist["reddedilen"]), inline=True)
    embed.set_footer(text="Kross Sentinel")
    await ctx.send(embed=embed)

# -------------------- HAZIR --------------------
@bot.event
async def on_ready():
    print(f"🛡️ {bot.user} aktif!")
    bot.add_view(TicketKontrol())
    bot.add_view(BasvuruButon())
    
    for guild in bot.guilds:
        destek_kanal = get(guild.text_channels, name=DESTEK_KANALI)
        basvuru_kanal = get(guild.text_channels, name=BASVURU_KANALI)
        oneri_kanal = get(guild.text_channels, name=ONERI_KANALI)
        
        if destek_kanal:
            async for msg in destek_kanal.history(limit=5):
                if msg.author == bot.user: await msg.delete()
            embed = discord.Embed(title="📩 DESTEK TALEBİ", description="Bir sorunla karşılaştıysan aşağıdaki butona tıkla.\n\n• Yetkililer en kısa sürede ilgilenecektir.\n• Gereksiz talep açanlar cezalandırılır.", color=0x00FF00)
            embed.set_footer(text="Kross Sentinel • Ticket")
            await destek_kanal.send(embed=embed, view=TicketKontrol())
        
        if basvuru_kanal:
            async for msg in basvuru_kanal.history(limit=5):
                if msg.author == bot.user: await msg.delete()
            embed = discord.Embed(title="📝 YETKİLİ BAŞVURUSU", description="Aramıza katılmak ister misin?\n\n• Dürüst ve detaylı cevaplar ver.\n• Sonuç DM ile bildirilecektir.", color=0x5865F2)
            embed.set_footer(text="Kross Sentinel • Başvuru")
            await basvuru_kanal.send(embed=embed, view=BasvuruButon())
        
        if oneri_kanal:
            async for msg in oneri_kanal.history(limit=5):
                if msg.author == bot.user: await msg.delete()
            embed = discord.Embed(title="💡 ÖNERİ SİSTEMİ", description="Sunucumuzu geliştirmek için önerilerinizi bekliyoruz!\n\n• Önerileriniz yetkililer tarafından değerlendirilecektir.\n• Sonuç DM ile bildirilecektir.", color=0xFFD700)
            embed.set_footer(text="Kross Sentinel • Öneri")
            await oneri_kanal.send(embed=embed, view=OneriButon())
    
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="sunucuyu | .yardim"))
    print("✅ Ticket, Başvuru, Öneri, Oylama, Puanlama hazır!")

# -------------------- YARDIM --------------------
@bot.command(name='yardim', aliases=['h'])
async def yardim(ctx):
    embed = discord.Embed(title="🛡️ KROSS SENTINEL", description="Profesyonel Yönetim Asistanı", color=0x5865F2, timestamp=datetime.now())
    embed.add_field(name="📩 Ticket", value="`🎫・destek` → Buton\n🤝 Al / ↩️ Vazgeç / ⭐ Puanla&Kapat\n`.ekle` `.cikar` `.kaydet` `.puanlar`", inline=False)
    embed.add_field(name="📝 Başvuru", value="`📝・başvuru` → Buton\n✅ Onay / ❌ Red / 💬 Yorum\n🔄 Yeniden Değerlendir", inline=False)
    embed.add_field(name="💡 Öneri", value="`önerim-var` → Buton\nOnay/Red/Yorum, DM bildirimi", inline=False)
    embed.add_field(name="🗳️ Oylama", value="`.oylama <dk> <soru>`", inline=False)
    embed.add_field(name="📊 İstatistik", value="`.istatistik` `.puanlar @yetkili`", inline=False)
    embed.set_footer(text="Kross Sentinel • Prefix: .")
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    elif isinstance(error, commands.MissingPermissions): await ctx.send("❌ Yetkin yok!")
    elif isinstance(error, commands.MissingRequiredArgument): await ctx.send("⚠️ Eksik! `.yardim`")

# -------------------- BAŞLAT --------------------
if __name__ == "__main__":
    Thread(target=run_flask).start()
    print("🛡️ Kross Sentinel başlatılıyor...")
    print("📩 Ticket | 📝 Başvuru | 💡 Öneri | 🗳️ Oylama | ⭐ Puanlama")
    print("👑 Özel Roller:", OZEL_ROLLER)
    TOKEN = os.environ.get('DISCORD_TOKEN')
    if TOKEN: bot.run(TOKEN)
    else: print("❌ Token bulunamadı!")
