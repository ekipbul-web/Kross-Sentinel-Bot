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
def home(): return "Kross Yönetim - Aktif"
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

VERI_DOSYASI = "yonetim_data.json"

# -------------------- VERİ --------------------
def veri_yukle():
    if os.path.exists(VERI_DOSYASI):
        with open(VERI_DOSYASI, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"tickets": {}, "basvurular": [], "istatistik": {"toplam_ticket": 0, "toplam_basvuru": 0, "onaylanan": 0, "reddedilen": 0}}

def veri_kaydet(veri):
    with open(VERI_DOSYASI, 'w', encoding='utf-8') as f:
        json.dump(veri, f, ensure_ascii=False, indent=2)

# -------------------- TİCKET SİSTEMİ --------------------
class TicketKontrol(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="📩 Talebi Aç", style=discord.ButtonStyle.green, custom_id="ticket_create", emoji="📩")
    async def ticket_create(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user
        
        kategori = get(guild.categories, name=TICKET_KATEGORI)
        if not kategori:
            try: kategori = await guild.create_category(TICKET_KATEGORI)
            except: return await interaction.response.send_message("❌ Kategori hatası!", ephemeral=True)
        
        for ch in guild.text_channels:
            if ch.name == f"🎫・{member.name.lower().replace(' ', '-')}":
                return await interaction.response.send_message(f"❌ Zaten açık: {ch.mention}", ephemeral=True)
        
        yetkili_rol = get(guild.roles, name=DESTEK_YETKILI)
        admin_rol = get(guild.roles, name="Admin")
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        if yetkili_rol: overwrites[yetkili_rol] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        if admin_rol: overwrites[admin_rol] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        kanal = await guild.create_text_channel(
            f"🎫・{member.name.lower().replace(' ', '-')}",
            category=kategori,
            topic=f"Ticket sahibi: {member.id} | Açılış: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            overwrites=overwrites
        )
        
        embed = discord.Embed(
            title="📩 DESTEK TALEBİ",
            description=f"**{member.mention}** bir destek talebi açtı!\n\n"
                       f"⏰ **Açılış:** <t:{int(datetime.now().timestamp())}:R>\n"
                       f"👤 **Sahip:** {member.mention}\n\n"
                       f"Yetkililer en kısa sürede ilgilenecektir.\n\n"
                       f"**Komutlar:**\n"
                       f"`.kapat` - Talebi kapat\n"
                       f"`.ekle @yetkili` - Yetkili ekle\n"
                       f"`.cikar @yetkili` - Yetkili çıkar\n"
                       f"`.kaydet` - Mesajları kaydet",
            color=0x00FF00,
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"Ticket ID: {kanal.id}")
        
        view = TicketYonetim(member)
        await kanal.send(embed=embed, view=view)
        await kanal.send(f"{member.mention} hoş geldin! {yetkili_rol.mention if yetkili_rol else ''} yetkililer etiketlendi.")
        
        veri = veri_yukle()
        veri["tickets"][str(kanal.id)] = {"sahip": member.id, "acilis": datetime.now().isoformat(), "durum": "açık"}
        veri["istatistik"]["toplam_ticket"] += 1
        veri_kaydet(veri)
        
        log_kanal = get(guild.text_channels, name=MOD_LOG)
        if log_kanal:
            await log_kanal.send(f"📩 Yeni ticket: {kanal.mention} - {member.mention}")
        
        await interaction.response.send_message(f"✅ Talep açıldı: {kanal.mention}", ephemeral=True)

class TicketYonetim(discord.ui.View):
    def __init__(self, sahip):
        super().__init__(timeout=None)
        self.sahip = sahip
    
    @discord.ui.button(label="🔒 Kapat", style=discord.ButtonStyle.red, custom_id="ticket_close", emoji="🔒")
    async def ticket_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith("🎫・"):
            return await interaction.response.send_message("❌ Ticket kanalı değil!", ephemeral=True)
        
        await interaction.response.send_message("🔒 Ticket 5 saniye içinde kapatılıyor...")
        await asyncio.sleep(5)
        
        veri = veri_yukle()
        if str(interaction.channel.id) in veri["tickets"]:
            veri["tickets"][str(interaction.channel.id)]["durum"] = "kapandı"
            veri_kaydet(veri)
        
        await interaction.channel.delete()
    
    @discord.ui.button(label="📄 Kaydet", style=discord.ButtonStyle.grey, custom_id="ticket_save", emoji="📄")
    async def ticket_save(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith("🎫・"):
            return await interaction.response.send_message("❌ Ticket kanalı değil!", ephemeral=True)
        
        messages = []
        async for msg in interaction.channel.history(limit=100, oldest_first=True):
            messages.append(f"[{msg.created_at.strftime('%H:%M')}] {msg.author.name}: {msg.content}")
        
        transcript = "\n".join(messages)
        
        log_kanal = get(interaction.guild.text_channels, name=MOD_LOG)
        if log_kanal and transcript:
            with open(f"transcript_{interaction.channel.id}.txt", "w", encoding="utf-8") as f:
                f.write(transcript)
            
            await log_kanal.send(
                f"📄 Ticket Transkript - {interaction.channel.name}",
                file=discord.File(f"transcript_{interaction.channel.id}.txt")
            )
            os.remove(f"transcript_{interaction.channel.id}.txt")
        
        await interaction.response.send_message("✅ Transkript kaydedildi!", ephemeral=True)

@bot.command(name='kapat')
async def ticket_kapat(ctx):
    if not ctx.channel.name.startswith("🎫・"):
        return await ctx.send("❌ Bu bir ticket kanalı değil!")
    
    await ctx.send("🔒 5 saniye içinde kapatılıyor...")
    await asyncio.sleep(5)
    
    veri = veri_yukle()
    if str(ctx.channel.id) in veri["tickets"]:
        veri["tickets"][str(ctx.channel.id)]["durum"] = "kapandı"
        veri_kaydet(veri)
    
    await ctx.channel.delete()

@bot.command(name='ekle')
@commands.has_permissions(manage_channels=True)
async def ticket_ekle(ctx, member: discord.Member):
    if not ctx.channel.name.startswith("🎫・"):
        return await ctx.send("❌ Ticket kanalı değil!")
    
    await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
    await ctx.send(f"✅ {member.mention} talebe eklendi!")

@bot.command(name='cikar')
@commands.has_permissions(manage_channels=True)
async def ticket_cikar(ctx, member: discord.Member):
    if not ctx.channel.name.startswith("🎫・"):
        return await ctx.send("❌ Ticket kanalı değil!")
    
    await ctx.channel.set_permissions(member, overwrite=None)
    await ctx.send(f"✅ {member.mention} talepden çıkarıldı!")

@bot.command(name='kaydet')
async def ticket_kaydet(ctx):
    if not ctx.channel.name.startswith("🎫・"):
        return await ctx.send("❌ Ticket kanalı değil!")
    
    messages = []
    async for msg in ctx.channel.history(limit=100, oldest_first=True):
        messages.append(f"[{msg.created_at.strftime('%H:%M')}] {msg.author.name}: {msg.content}")
    
    transcript = "\n".join(messages)
    
    log_kanal = get(ctx.guild.text_channels, name=MOD_LOG)
    if log_kanal and transcript:
        with open(f"transcript_{ctx.channel.id}.txt", "w", encoding="utf-8") as f:
            f.write(transcript)
        await log_kanal.send(f"📄 Transkript - {ctx.channel.name}", file=discord.File(f"transcript_{ctx.channel.id}.txt"))
        os.remove(f"transcript_{ctx.channel.id}.txt")
        await ctx.send("✅ Kaydedildi!")

# -------------------- BAŞVURU SİSTEMİ --------------------
class BasvuruButon(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
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
        if not log_kanal:
            return await interaction.response.send_message("❌ Başvuru log kanalı yok!", ephemeral=True)
        
        veri = veri_yukle()
        basvuru_no = len(veri["basvurular"]) + 1
        
        embed = discord.Embed(
            title=f"📝 YENİ BAŞVURU #{basvuru_no}",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        embed.add_field(name="👤 Başvuran", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
        embed.add_field(name="📛 Ad", value=self.isim.value, inline=True)
        embed.add_field(name="🎂 Yaş", value=self.yas.value, inline=True)
        embed.add_field(name="⏱️ Aktiflik", value=self.sure.value, inline=True)
        embed.add_field(name="📜 Tecrübe", value=self.tecrube.value, inline=False)
        embed.add_field(name="❓ Neden", value=self.neden.value, inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Kross Yönetim • Başvuru Sistemi")
        
        veri["basvurular"].append({
            "no": basvuru_no,
            "kullanici_id": interaction.user.id,
            "isim": self.isim.value,
            "yas": self.yas.value,
            "tecrube": self.tecrube.value,
            "neden": self.neden.value,
            "sure": self.sure.value,
            "durum": "bekliyor",
            "tarih": datetime.now().isoformat()
        })
        veri["istatistik"]["toplam_basvuru"] += 1
        veri_kaydet(veri)
        
        yetkili_rol = get(guild.roles, name=BASVURU_YETKILI)
        view = BasvuruDegerlendir(interaction.user, basvuru_no)
        
        await log_kanal.send(
            f"{yetkili_rol.mention if yetkili_rol else ''} Yeni başvuru!",
            embed=embed,
            view=view
        )
        
        try:
            dm_embed = discord.Embed(
                title="✅ Başvurun Alındı!",
                description=f"{guild.name} sunucusuna yaptığın yetkili başvurusu alındı.\nBaşvuru No: **#{basvuru_no}**\nDurum: **Beklemede**",
                color=0x00FF00
            )
            dm_embed.set_footer(text="Sonuç DM ile bildirilecek")
            await interaction.user.send(embed=dm_embed)
        except:
            pass
        
        await interaction.response.send_message("✅ Başvurun alındı! DM kutunu kontrol et.", ephemeral=True)

class BasvuruDegerlendir(discord.ui.View):
    def __init__(self, basvuran, basvuru_no):
        super().__init__(timeout=None)
        self.basvuran = basvuran
        self.basvuru_no = basvuru_no
    
    @discord.ui.button(label="✅ Onayla", style=discord.ButtonStyle.green, custom_id="basvuru_onayla")
    async def onayla(self, interaction: discord.Interaction, button: discord.ui.Button):
        veri = veri_yukle()
        for b in veri["basvurular"]:
            if b["no"] == self.basvuru_no:
                b["durum"] = "onaylandı"
                break
        veri["istatistik"]["onaylanan"] += 1
        veri_kaydet(veri)
        
        try:
            await self.basvuran.send(f"🎉 Tebrikler! **{interaction.guild.name}** sunucusuna yetkili başvurun **ONAYLANDI!**")
        except: pass
        
        button.disabled = True
        self.children[1].disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message(f"✅ #{self.basvuru_no} onaylandı! DM bildirildi.")
    
    @discord.ui.button(label="❌ Reddet", style=discord.ButtonStyle.red, custom_id="basvuru_reddet")
    async def reddet(self, interaction: discord.Interaction, button: discord.ui.Button):
        veri = veri_yukle()
        for b in veri["basvurular"]:
            if b["no"] == self.basvuru_no:
                b["durum"] = "reddedildi"
                break
        veri["istatistik"]["reddedilen"] += 1
        veri_kaydet(veri)
        
        try:
            await self.basvuran.send(f"❌ Üzgünüz! **{interaction.guild.name}** sunucusuna başvurun **REDDEDİLDİ.**")
        except: pass
        
        button.disabled = True
        self.children[0].disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message(f"❌ #{self.basvuru_no} reddedildi! DM bildirildi.")
    
    @discord.ui.button(label="💬 Yorum Ekle", style=discord.ButtonStyle.grey, custom_id="basvuru_yorum")
    async def yorum(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = YorumModal(self.basvuran, self.basvuru_no)
        await interaction.response.send_modal(modal)

class YorumModal(discord.ui.Modal, title="💬 Başvuru Yorumu"):
    yorum = discord.ui.TextInput(label="Yorumun", placeholder="Başvuru hakkında yorum yaz...", required=True, style=discord.TextStyle.paragraph)
    
    def __init__(self, basvuran, basvuru_no):
        super().__init__()
        self.basvuran = basvuran
        self.basvuru_no = basvuru_no
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            await self.basvuran.send(f"💬 Başvurun #{self.basvuru_no} hakkında yorum:\n\n**{self.yorum.value}**")
        except: pass
        await interaction.response.send_message("✅ Yorum DM ile gönderildi!", ephemeral=True)

# -------------------- OYLAMA --------------------
@bot.command(name='oylama')
@commands.has_permissions(manage_messages=True)
async def oylama(ctx, sure: int = 0, *, soru: str):
    """Oylama başlatır: .oylama <dakika> <soru> (0=süresiz)"""
    await ctx.message.delete()
    
    embed = discord.Embed(
        title="🗳️ OYLAMA",
        description=soru,
        color=0x5865F2,
        timestamp=datetime.now()
    )
    embed.add_field(name="⏱️ Süre", value=f"{sure} dakika" if sure > 0 else "Süresiz", inline=True)
    embed.add_field(name="👤 Açan", value=ctx.author.mention, inline=True)
    embed.set_footer(text="✅ Evet • ❌ Hayır • 🤷 Çekimser")
    
    msg = await ctx.send("@everyone", embed=embed)
    await msg.add_reaction("✅")
    await msg.add_reaction("❌")
    await msg.add_reaction("🤷")
    
    if sure > 0:
        await asyncio.sleep(sure * 60)
        
        msg = await ctx.channel.fetch_message(msg.id)
        evet = hayir = cekimser = 0
        
        for r in msg.reactions:
            if str(r.emoji) == "✅": evet = r.count - 1
            elif str(r.emoji) == "❌": hayir = r.count - 1
            elif str(r.emoji) == "🤷": cekimser = r.count - 1
        
        sonuc = discord.Embed(
            title="🗳️ OYLAMA SONUCU",
            description=soru,
            color=0x00FF00 if evet > hayir else 0xFF0000,
            timestamp=datetime.now()
        )
        sonuc.add_field(name="✅ Evet", value=str(evet), inline=True)
        sonuc.add_field(name="❌ Hayır", value=str(hayir), inline=True)
        sonuc.add_field(name="🤷 Çekimser", value=str(cekimser), inline=True)
        sonuc.set_footer(text="Oylama sona erdi!")
        
        await ctx.send(embed=sonuc)

# -------------------- İSTATİSTİK --------------------
@bot.command(name='istatistik')
@commands.has_permissions(manage_messages=True)
async def istatistik(ctx):
    veri = veri_yukle()
    ist = veri["istatistik"]
    
    embed = discord.Embed(title="📊 YÖNETİM İSTATİSTİKLERİ", color=0x5865F2, timestamp=datetime.now())
    embed.add_field(name="📩 Toplam Ticket", value=str(ist["toplam_ticket"]), inline=True)
    embed.add_field(name="📝 Toplam Başvuru", value=str(ist["toplam_basvuru"]), inline=True)
    embed.add_field(name="✅ Onaylanan", value=str(ist["onaylanan"]), inline=True)
    embed.add_field(name="❌ Reddedilen", value=str(ist["reddedilen"]), inline=True)
    embed.add_field(name="📋 Bekleyen", value=str(ist["toplam_basvuru"] - ist["onaylanan"] - ist["reddedilen"]), inline=True)
    
    acik_ticket = sum(1 for t in veri["tickets"].values() if t["durum"] == "açık")
    embed.add_field(name="🔓 Açık Ticket", value=str(acik_ticket), inline=True)
    embed.set_footer(text="Kross Yönetim • İstatistik")
    
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
        
        if destek_kanal:
            async for msg in destek_kanal.history(limit=5):
                if msg.author == bot.user:
                    await msg.delete()
            
            embed = discord.Embed(
                title="📩 DESTEK TALEBİ",
                description="Bir sorunla karşılaştıysan veya yetkiliye ulaşmak istiyorsan "
                           "aşağıdaki butona tıklayarak özel destek talebi oluşturabilirsin.\n\n"
                           "• Yetkililer en kısa sürede ilgilenecektir.\n"
                           "• Gereksiz talep açanlar cezalandırılır.\n"
                           "• Talebi kapatmak için `.kapat` yazabilirsin.\n"
                           "• `.kaydet` ile mesajları kaydedebilirsin.",
                color=0x00FF00
            )
            embed.set_footer(text="Kross Yönetim • Ticket Sistemi")
            await destek_kanal.send(embed=embed, view=TicketKontrol())
        
        if basvuru_kanal:
            async for msg in basvuru_kanal.history(limit=5):
                if msg.author == bot.user:
                    await msg.delete()
            
            embed = discord.Embed(
                title="📝 YETKİLİ BAŞVURUSU",
                description="Aramıza katılmak ve yetkili olmak ister misin?\n\n"
                           "Aşağıdaki butona tıklayarak başvuru formunu doldurabilirsin.\n\n"
                           "• Dürüst ve detaylı cevaplar ver.\n"
                           "• Başvurun yetkililer tarafından değerlendirilecektir.\n"
                           "• Sonuç DM ile bildirilecektir.\n"
                           "• Yorumlar DM üzerinden iletilecektir.",
                color=0x5865F2
            )
            embed.set_footer(text="Kross Yönetim • Başvuru Sistemi")
            await basvuru_kanal.send(embed=embed, view=BasvuruButon())
    
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="sunucuyu | .yardim"))
    print("✅ Tüm sistemler hazır!")

# -------------------- YARDIM --------------------
@bot.command(name='yardim', aliases=['h'])
async def yardim(ctx):
    embed = discord.Embed(
        title="🛡️ KROSS YÖNETİM BOTU",
        description="Profesyonel Yönetim Asistanı",
        color=0x5865F2,
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="📩 **Ticket Sistemi**",
        value="`🎫・destek` kanalından talep aç\n"
              "`.kapat` - Talebi kapat\n"
              "`.ekle @kişi` - Yetkili ekle\n"
              "`.cikar @kişi` - Yetkili çıkar\n"
              "`.kaydet` - Transkript kaydet",
        inline=False
    )
    
    embed.add_field(
        name="📝 **Başvuru Sistemi**",
        value="`📝・başvuru` kanalından başvur\n"
              "• Form doldurma\n"
              "• DM bildirimi\n"
              "• Yorum ekleme\n"
              "• Onay/Red butonları",
        inline=False
    )
    
    embed.add_field(
        name="🗳️ **Oylama Sistemi**",
        value="`.oylama <dakika> <soru>` - Süreli oylama\n"
              "`.oylama 0 <soru>` - Süresiz oylama\n"
              "• Otomatik sonuç açıklama",
        inline=False
    )
    
    embed.add_field(
        name="📊 **İstatistik**",
        value="`.istatistik` - Tüm istatistikleri gör",
        inline=False
    )
    
    embed.set_footer(text="Kross Yönetim • Prefix: .")
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    elif isinstance(error, commands.MissingPermissions): await ctx.send("❌ Yetkin yok!")
    elif isinstance(error, commands.MissingRequiredArgument): await ctx.send("⚠️ Eksik! `.yardim`")

# -------------------- BAŞLAT --------------------
if __name__ == "__main__":
    Thread(target=run_flask).start()
    print("🛡️ Kross Yönetim Botu başlatılıyor...")
    TOKEN = os.environ.get('DISCORD_TOKEN')
    if TOKEN: bot.run(TOKEN)
    else: print("❌ Token bulunamadı!")
