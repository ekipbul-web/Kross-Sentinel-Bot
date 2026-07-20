import discord
from discord.ext import commands
from discord.utils import get
import asyncio
from datetime import datetime, timedelta
import json
import os
import uuid
import logging
from flask import Flask
from threading import Thread

# Logging ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Flask uygulaması
app = Flask(__name__)

@app.route('/')
def home():
    return "Kross Sentinel - Aktif"

def run_flask():
    try:
        app.run(host='0.0.0.0', port=8080, debug=False)
    except Exception as e:
        logger.error(f"Flask başlatılamadı: {e}")

# Discord bot ayarları
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

# -------------------- VERİ YÖNETİMİ --------------------
import threading
veri_lock = threading.Lock()

def veri_yukle():
    """Veri dosyasını güvenli şekilde yükle"""
    with veri_lock:
        try:
            if os.path.exists(VERI_DOSYASI):
                with open(VERI_DOSYASI, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Veri yükleme hatası: {e}")
    
    return {
        "tickets": {},
        "basvurular": [],
        "basvuru_sayac": 0,
        "oneriler": [],
        "oneri_sayac": 0,
        "puanlar": {},
        "istatistik": {
            "toplam_ticket": 0,
            "toplam_basvuru": 0,
            "onaylanan": 0,
            "reddedilen": 0,
            "toplam_oneri": 0
        }
    }

def veri_kaydet(veri):
    """Veri dosyasını güvenli şekilde kaydet"""
    with veri_lock:
        try:
            with open(VERI_DOSYASI, 'w', encoding='utf-8') as f:
                json.dump(veri, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"Veri kaydetme hatası: {e}")

def ozel_rol_kontrol(member):
    """Özel rol kontrolü"""
    if not member or not member.guild:
        return False
    
    for rol_adi in OZEL_ROLLER:
        rol = get(member.guild.roles, name=rol_adi)
        if rol and rol in member.roles:
            return True
    return False

async def guvenli_dm_gonder(member, embed):
    """Güvenli DM gönderme"""
    try:
        await member.send(embed=embed)
        return True
    except discord.Forbidden:
        logger.warning(f"DM gönderilemedi: {member.id}")
        return False
    except discord.HTTPException as e:
        logger.error(f"DM HTTP hatası: {e}")
        return False

# -------------------- TICKET SİSTEMİ --------------------
async def ticket_kapat(interaction, ticket, puan=None, yorum=None):
    """Ticket'ı güvenli şekilde kapat"""
    if not ticket:
        await interaction.response.send_message("❌ Ticket bilgisi bulunamadı!", ephemeral=True)
        return
    
    try:
        # Transkript kaydet
        messages = []
        async for msg in interaction.channel.history(limit=None):
            messages.append(f"[{msg.created_at.strftime('%H:%M')}] {msg.author.name}: {msg.content}")
        messages.reverse()  # En eski mesaj başa
        
        transcript = "\n".join(messages)
        transcript_dosya = None
        
        if transcript:
            dosya_adi = f"transcript_{interaction.channel.id}_{uuid.uuid4().hex[:8]}.txt"
            with open(dosya_adi, "w", encoding="utf-8") as f:
                f.write(transcript)
            transcript_dosya = discord.File(dosya_adi)
        
        # Süre hesapla
        try:
            acilis = datetime.fromisoformat(ticket["acilis"])
            kapanis = datetime.now()
            sure = kapanis - acilis
            
            saat = sure.seconds // 3600
            dakika = (sure.seconds % 3600) // 60
            saniye = sure.seconds % 60
            
            if saat > 0:
                sure_str = f"{saat}s {dakika}dk {saniye}sn"
            elif dakika > 0:
                sure_str = f"{dakika}dk {saniye}sn"
            else:
                sure_str = f"{saniye}sn"
        except:
            sure_str = "❌ Hesaplanamadı"
        
        # Ticket sahibi
        sahip = interaction.guild.get_member(ticket["sahip"])
        sahip_adi = sahip.mention if sahip else f"Kullanıcı ID: {ticket['sahip']}"
        
        # İlgilenen yetkili
        alan_adi = "❌ Alınmadı"
        if ticket.get("alan"):
            alan = interaction.guild.get_member(ticket["alan"])
            alan_adi = alan.mention if alan else f"Yetkili ID: {ticket['alan']}"
        
        # Log embed'i
        log_embed = discord.Embed(
            title="🔒 TICKET KAPATILDI",
            color=0xFF0000,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="📋 Kanal", value=f"`{interaction.channel.name}`", inline=True)
        log_embed.add_field(name="👤 Açan", value=sahip_adi, inline=True)
        log_embed.add_field(name="🤝 İlgilenen", value=alan_adi, inline=True)
        
        if 'acilis' in ticket:
            try:
                log_embed.add_field(name="📅 Açılış", value=f"<t:{int(datetime.fromisoformat(ticket['acilis']).timestamp())}:F>", inline=True)
            except:
                log_embed.add_field(name="📅 Açılış", value="❌ Bilinmiyor", inline=True)
        
        log_embed.add_field(name="🔒 Kapanış", value=f"<t:{int(datetime.now().timestamp())}:F>", inline=True)
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
        if transcript_dosya:
            try:
                os.remove(dosya_adi)
            except:
                pass
        
        # Ticket'ı veriden sil
        veri = veri_yukle()
        if str(interaction.channel.id) in veri["tickets"]:
            del veri["tickets"][str(interaction.channel.id)]
        veri_kaydet(veri)
        
        # Kanalı sil
        try:
            await interaction.channel.delete()
        except discord.Forbidden:
            logger.error(f"Kanal silme yetkisi yok: {interaction.channel.id}")
            await interaction.followup.send("❌ Kanal silinemedi, lütfen manuel silin!", ephemeral=True)
        except discord.HTTPException as e:
            logger.error(f"Kanal silme HTTP hatası: {e}")
            
    except Exception as e:
        logger.error(f"Ticket kapatma hatası: {e}")
        try:
            await interaction.response.send_message("❌ Ticket kapatılırken bir hata oluştu!", ephemeral=True)
        except:
            pass

class PuanModal(discord.ui.Modal, title="⭐ Yetkiliyi Puanla"):
    def __init__(self, yetkili_id, yetkili_adi, ticket_id):
        super().__init__()
        self.yetkili_id = yetkili_id
        self.yetkili_adi = yetkili_adi
        self.ticket_id = ticket_id
    
    puan = discord.ui.TextInput(
        label="Puan (1-5)",
        placeholder="1-5 arası yıldız ver...",
        required=True,
        max_length=1
    )
    
    yorum = discord.ui.TextInput(
        label="Yorum (opsiyonel)",
        placeholder="Yetkili hakkında yorum...",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=200
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        if not self.puan.value.isdigit() or not (1 <= int(self.puan.value) <= 5):
            return await interaction.response.send_message("❌ 1-5 arası bir sayı gir!", ephemeral=True)
        
        puan = int(self.puan.value)
        veri = veri_yukle()
        
        if "puanlar" not in veri:
            veri["puanlar"] = {}
        
        if str(self.yetkili_id) not in veri["puanlar"]:
            veri["puanlar"][str(self.yetkili_id)] = {
                "isim": self.yetkili_adi,
                "toplam": 0,
                "sayi": 0,
                "yorumlar": []
            }
        
        veri["puanlar"][str(self.yetkili_id)]["toplam"] += puan
        veri["puanlar"][str(self.yetkili_id)]["sayi"] += 1
        
        if self.yorum.value:
            veri["puanlar"][str(self.yetkili_id)]["yorumlar"].append({
                "puan": puan,
                "yorum": self.yorum.value,
                "tarih": datetime.now().isoformat()
            })
        
        veri_kaydet(veri)
        
        # Ticket'ı kapat
        ticket = veri["tickets"].get(self.ticket_id)
        await ticket_kapat(interaction, ticket, puan, self.yorum.value)

class TicketKontrol(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="📩 Talebi Aç", style=discord.ButtonStyle.green, custom_id="ticket_create", emoji="📩")
    async def ticket_create(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        member = interaction.user
        
        # Kategori kontrolü
        kategori = get(guild.categories, name=TICKET_KATEGORI)
        if not kategori:
            try:
                kategori = await guild.create_category(TICKET_KATEGORI)
            except discord.Forbidden:
                return await interaction.followup.send("❌ Kategori oluşturma yetkisi yok!", ephemeral=True)
            except discord.HTTPException:
                return await interaction.followup.send("❌ Kategori oluşturulamadı!", ephemeral=True)
        
        # Açık ticket kontrolü - daha güvenli
        kanal_adi = f"🎫・{member.name.lower().replace(' ', '-')}"
        for ch in guild.text_channels:
            if ch.name.lower() == kanal_adi.lower() and ch.category == kategori:
                return await interaction.followup.send(f"❌ Zaten açık bir ticket'ınız var: {ch.mention}", ephemeral=True)
        
        # Yetkili rolü
        yetkili_rol = get(guild.roles, name=DESTEK_YETKILI)
        
        # İzin ayarları
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        if yetkili_rol:
            overwrites[yetkili_rol] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        for rol_adi in OZEL_ROLLER:
            ozel_rol = get(guild.roles, name=rol_adi)
            if ozel_rol:
                overwrites[ozel_rol] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        try:
            kanal = await guild.create_text_channel(
                kanal_adi,
                category=kategori,
                topic=f"Ticket sahibi: {member.id} | Alan: Yok",
                overwrites=overwrites
            )
        except Exception as e:
            logger.error(f"Kanal oluşturma hatası: {e}")
            return await interaction.followup.send("❌ Ticket kanalı oluşturulamadı!", ephemeral=True)
        
        # Embed mesajı
        embed = discord.Embed(
            title="📩 DESTEK TALEBİ",
            description=f"**{member.mention}** bir destek talebi açtı!\n\n"
                       f"⏰ <t:{int(datetime.now().timestamp())}:R>\n"
                       f"👤 {member.mention}\n"
                       f"🤝 **Alan:** Henüz alınmadı\n\n"
                       f"`.ekle` / `.cikar` / `.kaydet`",
            color=0x00FF00,
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"Ticket ID: {kanal.id}")
        
        await kanal.send(embed=embed, view=TicketYonetim(member.id))
        
        if yetkili_rol:
            await kanal.send(f"{member.mention} hoş geldin! {yetkili_rol.mention} en kısa sürede ilgilenecektir.")
        else:
            await kanal.send(f"{member.mention} hoş geldin! Yetkililer en kısa sürede ilgilenecektir.")
        
        # Veri kaydet
        veri = veri_yukle()
        veri["tickets"][str(kanal.id)] = {
            "sahip": member.id,
            "alan": None,
            "acilis": datetime.now().isoformat(),
            "durum": "açık"
        }
        veri["istatistik"]["toplam_ticket"] += 1
        veri_kaydet(veri)
        
        await interaction.followup.send(f"✅ Talep açıldı: {kanal.mention}", ephemeral=True)

class TicketYonetim(discord.ui.View):
    def __init__(self, sahip_id):
        super().__init__(timeout=None)
        self.sahip_id = sahip_id
    
    @discord.ui.button(label="🤝 Ticketi Al", style=discord.ButtonStyle.blurple, custom_id="ticket_al_btn", emoji="🤝")
    async def ticket_al(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith("🎫・"):
            return await interaction.response.send_message("❌ Bu bir ticket kanalı değil!", ephemeral=True)
        
        veri = veri_yukle()
        ticket = veri["tickets"].get(str(interaction.channel.id))
        
        if not ticket:
            return await interaction.response.send_message("❌ Ticket bilgisi bulunamadı!", ephemeral=True)
        
        if ticket["alan"] is not None:
            alan = interaction.guild.get_member(ticket["alan"])
            return await interaction.response.send_message(
                f"❌ Bu ticket zaten {alan.mention if alan else 'bir yetkili'} tarafından alınmış!",
                ephemeral=True
            )
        
        # Yetki kontrolü
        yetkili_rol = get(interaction.guild.roles, name=DESTEK_YETKILI)
        is_yetkili = yetkili_rol and yetkili_rol in interaction.user.roles
        is_ozel = ozel_rol_kontrol(interaction.user)
        
        if not is_yetkili and not is_ozel:
            return await interaction.response.send_message("❌ Bu ticket'ı almak için yetkiniz yok!", ephemeral=True)
        
        # Ticket'ı al
        ticket["alan"] = interaction.user.id
        veri_kaydet(veri)
        
        # Diğer yetkilileri sustur
        if yetkili_rol:
            for member in yetkili_rol.members:
                if member.id != interaction.user.id and not ozel_rol_kontrol(member):
                    try:
                        await interaction.channel.set_permissions(member, send_messages=False)
                    except:
                        pass
        
        # Kanal konusunu güncelle
        await interaction.channel.edit(topic=f"Ticket sahibi: {ticket['sahip']} | Alan: {interaction.user.id}")
        
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🤝 Ticket Alındı",
                description=f"**{interaction.user.mention}** bu ticket'i aldı!",
                color=0x5865F2
            ).set_footer(text="↩️ Vazgeç ile bırakabilirsin")
        )
    
    @discord.ui.button(label="↩️ Vazgeç", style=discord.ButtonStyle.grey, custom_id="ticket_vazgec_btn", emoji="↩️")
    async def ticket_vazgec(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith("🎫・"):
            return await interaction.response.send_message("❌ Bu bir ticket kanalı değil!", ephemeral=True)
        
        veri = veri_yukle()
        ticket = veri["tickets"].get(str(interaction.channel.id))
        
        if not ticket:
            return await interaction.response.send_message("❌ Ticket bilgisi bulunamadı!", ephemeral=True)
        
        if ticket["alan"] != interaction.user.id:
            return await interaction.response.send_message("❌ Bu ticket'i siz almamışsınız!", ephemeral=True)
        
        # Vazgeç
        ticket["alan"] = None
        veri_kaydet(veri)
        
        # Yetkililerin izinlerini geri ver
        yetkili_rol = get(interaction.guild.roles, name=DESTEK_YETKILI)
        if yetkili_rol:
            for member in yetkili_rol.members:
                try:
                    await interaction.channel.set_permissions(member, send_messages=True)
                except:
                    pass
        
        # Kanal konusunu güncelle
        await interaction.channel.edit(topic=f"Ticket sahibi: {ticket['sahip']} | Alan: Yok")
        
        await interaction.response.send_message(
            embed=discord.Embed(
                title="↩️ Vazgeçildi",
                description=f"**{interaction.user.mention}** ticket'ten vazgeçti. Başka bir yetkili alabilir!",
                color=0xFFA500
            )
        )
    
    @discord.ui.button(label="⭐ Puanla & Kapat", style=discord.ButtonStyle.red, custom_id="ticket_close_btn", emoji="⭐")
    async def ticket_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith("🎫・"):
            return await interaction.response.send_message("❌ Bu bir ticket kanalı değil!", ephemeral=True)
        
        veri = veri_yukle()
        ticket = veri["tickets"].get(str(interaction.channel.id))
        
        if not ticket:
            return await interaction.response.send_message("❌ Ticket bilgisi bulunamadı!", ephemeral=True)
        
        # Yetki kontrolü
        is_ozel = ozel_rol_kontrol(interaction.user)
        is_sahip = ticket["sahip"] == interaction.user.id
        is_alan = ticket.get("alan") == interaction.user.id
        
        if not is_ozel and not is_sahip and not is_alan:
            return await interaction.response.send_message("❌ Bu ticket'i kapatmaya yetkiniz yok!", ephemeral=True)
        
        # Ticket sahibi puanlama yapabilir (eğer ticket'i alan biri varsa)
        if is_sahip and ticket.get("alan") and ticket["alan"] != interaction.user.id:
            yetkili = interaction.guild.get_member(ticket["alan"])
            if yetkili:
                modal = PuanModal(ticket["alan"], yetkili.display_name, str(interaction.channel.id))
                return await interaction.response.send_modal(modal)
        
        # Direkt kapat
        await ticket_kapat(interaction, ticket)
    
    @discord.ui.button(label="📄 Kaydet", style=discord.ButtonStyle.grey, custom_id="ticket_save_btn", emoji="📄")
    async def ticket_save(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith("🎫・"):
            return await interaction.response.send_message("❌ Bu bir ticket kanalı değil!", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            messages = []
            async for msg in interaction.channel.history(limit=None):
                messages.append(f"[{msg.created_at.strftime('%H:%M')}] {msg.author.name}: {msg.content}")
            messages.reverse()
            
            transcript = "\n".join(messages)
            log_kanal = get(interaction.guild.text_channels, name=MOD_LOG)
            
            if log_kanal and transcript:
                dosya_adi = f"transcript_{interaction.channel.id}_{uuid.uuid4().hex[:8]}.txt"
                with open(dosya_adi, "w", encoding="utf-8") as f:
                    f.write(transcript)
                
                await log_kanal.send(
                    f"📄 Transkript - {interaction.channel.name}",
                    file=discord.File(dosya_adi)
                )
                
                try:
                    os.remove(dosya_adi)
                except:
                    pass
                
                await interaction.followup.send("✅ Transkript kaydedildi!", ephemeral=True)
            else:
                await interaction.followup.send("❌ Log kanalı bulunamadı veya transkript boş!", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Transkript kaydetme hatası: {e}")
            await interaction.followup.send("❌ Transkript kaydedilirken hata oluştu!", ephemeral=True)

# Ticket komutları
@bot.command(name='ekle')
async def ticket_ekle(ctx, member: discord.Member):
    if not ctx.channel.name.startswith("🎫・"):
        return await ctx.send("❌ Bu bir ticket kanalı değil!")
    
    veri = veri_yukle()
    ticket = veri["tickets"].get(str(ctx.channel.id))
    
    if not ticket:
        return await ctx.send("❌ Ticket bilgisi bulunamadı!")
    
    is_ozel = ozel_rol_kontrol(ctx.author)
    is_alan = ticket.get("alan") == ctx.author.id
    
    if not is_ozel and not is_alan:
        return await ctx.send("❌ Bu ticket üzerinde işlem yapma yetkiniz yok!")
    
    try:
        await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
        await ctx.send(f"✅ {member.mention} ticket'a eklendi!")
    except Exception as e:
        await ctx.send(f"❌ Kullanıcı eklenirken hata oluştu: {e}")

@bot.command(name='cikar')
async def ticket_cikar(ctx, member: discord.Member):
    if not ctx.channel.name.startswith("🎫・"):
        return await ctx.send("❌ Bu bir ticket kanalı değil!")
    
    veri = veri_yukle()
    ticket = veri["tickets"].get(str(ctx.channel.id))
    
    if not ticket:
        return await ctx.send("❌ Ticket bilgisi bulunamadı!")
    
    is_ozel = ozel_rol_kontrol(ctx.author)
    is_alan = ticket.get("alan") == ctx.author.id
    
    if not is_ozel and not is_alan:
        return await ctx.send("❌ Bu ticket üzerinde işlem yapma yetkiniz yok!")
    
    try:
        await ctx.channel.set_permissions(member, overwrite=None)
        await ctx.send(f"✅ {member.mention} ticket'tan çıkarıldı!")
    except Exception as e:
        await ctx.send(f"❌ Kullanıcı çıkarılırken hata oluştu: {e}")

@bot.command(name='kaydet')
async def ticket_kaydet(ctx):
    if not ctx.channel.name.startswith("🎫・"):
        return await ctx.send("❌ Bu bir ticket kanalı değil!")
    
    try:
        messages = []
        async for msg in ctx.channel.history(limit=None):
            messages.append(f"[{msg.created_at.strftime('%H:%M')}] {msg.author.name}: {msg.content}")
        messages.reverse()
        
        transcript = "\n".join(messages)
        log_kanal = get(ctx.guild.text_channels, name=MOD_LOG)
        
        if log_kanal and transcript:
            dosya_adi = f"transcript_{ctx.channel.id}_{uuid.uuid4().hex[:8]}.txt"
            with open(dosya_adi, "w", encoding="utf-8") as f:
                f.write(transcript)
            
            await log_kanal.send(
                f"📄 Transkript - {ctx.channel.name}",
                file=discord.File(dosya_adi)
            )
            
            try:
                os.remove(dosya_adi)
            except:
                pass
            
            await ctx.send("✅ Transkript kaydedildi!")
        else:
            await ctx.send("❌ Log kanalı bulunamadı!")
            
    except Exception as e:
        logger.error(f"Transkript kaydetme hatası: {e}")
        await ctx.send(f"❌ Hata oluştu: {e}")

@bot.command(name='puanlar')
async def puanlar(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    
    veri = veri_yukle()
    puan_data = veri.get("puanlar", {}).get(str(member.id))
    
    if not puan_data or puan_data["sayi"] == 0:
        return await ctx.send(f"❌ {member.mention} henüz puanlanmamış!")
    
    ortalama = puan_data["toplam"] / puan_data["sayi"]
    yildizlar = "⭐" * round(ortalama) + "☆" * (5 - round(ortalama))
    
    embed = discord.Embed(
        title=f"⭐ {member.display_name} Puanları",
        color=0xFFD700,
        timestamp=datetime.now()
    )
    embed.add_field(name="📊 Ortalama", value=f"**{ortalama:.1f}/5** {yildizlar}", inline=False)
    embed.add_field(name="📝 Toplam Oy", value=str(puan_data["sayi"]), inline=True)
    embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else member.default_avatar.url)
    
    if puan_data.get("yorumlar"):
        yorumlar = "\n".join([
            f"⭐{y['puan']} - {y['yorum'][:50]}" 
            for y in puan_data["yorumlar"][-3:]
        ])
        embed.add_field(name="💬 Son Yorumlar", value=yorumlar or "Yorum yok", inline=False)
    
    await ctx.send(embed=embed)

# -------------------- BAŞVURU SİSTEMİ --------------------
class BasvuruButon(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="📝 Yetkili Başvurusu", style=discord.ButtonStyle.blurple, custom_id="basvuru_btn", emoji="📝")
    async def basvuru_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BasvuruModal())

class BasvuruModal(discord.ui.Modal, title="📝 YETKİLİ BAŞVURU FORMU"):
    isim = discord.ui.TextInput(
        label="Gerçek Adın",
        placeholder="Adını yaz",
        required=True
    )
    
    yas = discord.ui.TextInput(
        label="Yaşın",
        placeholder="Örn: 18",
        required=True,
        max_length=2
    )
    
    tecrube = discord.ui.TextInput(
        label="Daha önce yetkili oldun mu?",
        placeholder="Hangi sunucularda yetkiliydin?",
        required=True,
        style=discord.TextStyle.paragraph
    )
    
    neden = discord.ui.TextInput(
        label="Neden yetkili olmak istiyorsun?",
        placeholder="Kendini ve hedeflerini anlat",
        required=True,
        style=discord.TextStyle.paragraph
    )
    
    sure = discord.ui.TextInput(
        label="Günde kaç saat aktifsin?",
        placeholder="Örn: 5-6 saat",
        required=True,
        max_length=20
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        log_kanal = get(guild.text_channels, name=BASVURU_LOG)
        
        if not log_kanal:
            return await interaction.response.send_message("❌ Başvuru log kanalı bulunamadı!", ephemeral=True)
        
        veri = veri_yukle()
        
        # Güvenli sayaç
        if "basvuru_sayac" not in veri:
            veri["basvuru_sayac"] = 0
        veri["basvuru_sayac"] += 1
        basvuru_no = veri["basvuru_sayac"]
        
        embed = discord.Embed(
            title=f"📝 YENİ BAŞVURU #{basvuru_no}",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        embed.add_field(name="👤 Başvuran", value=f"{interaction.user.mention}", inline=False)
        embed.add_field(name="📛 Ad", value=self.isim.value, inline=True)
        embed.add_field(name="🎂 Yaş", value=self.yas.value, inline=True)
        embed.add_field(name="⏱️ Aktiflik", value=self.sure.value, inline=True)
        embed.add_field(name="📜 Tecrübe", value=self.tecrube.value, inline=False)
        embed.add_field(name="❓ Neden", value=self.neden.value, inline=False)
        embed.add_field(name="📊 Durum", value="⏳ Beklemede", inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url if interaction.user.display_avatar else interaction.user.default_avatar.url)
        embed.set_footer(text="Kross Sentinel • Başvuru")
        
        veri["basvurular"].append({
            "no": basvuru_no,
            "kullanici_id": interaction.user.id,
            "isim": self.isim.value,
            "yas": self.yas.value,
            "tecrube": self.tecrube.value,
            "neden": self.neden.value,
            "sure": self.sure.value,
            "durum": "bekliyor",
            "yorumlar": [],
            "tarih": datetime.now().isoformat()
        })
        veri["istatistik"]["toplam_basvuru"] += 1
        veri_kaydet(veri)
        
        yetkili_rol = get(guild.roles, name=BASVURU_YETKILI)
        mention = f"{yetkili_rol.mention}" if yetkili_rol else "@everyone"
        
        await log_kanal.send(
            f"{mention} Yeni başvuru!",
            embed=embed,
            view=BasvuruDegerlendir(interaction.user.id, basvuru_no)
        )
        
        # DM bildirimi
        dm_embed = discord.Embed(
            title="✅ Başvurunuz Alındı!",
            description=f"**{guild.name}** sunucusuna başvurunuz iletilmiştir.",
            color=0x00FF00
        )
        dm_embed.add_field(name="📋 Başvuru No", value=f"#{basvuru_no}")
        dm_embed.add_field(name="📊 Durum", value="⏳ Beklemede")
        dm_embed.set_footer(text="Sonuç DM ile bildirilecektir.")
        
        await guvenli_dm_gonder(interaction.user, dm_embed)
        await interaction.response.send_message("✅ Başvurunuz alındı! Sonuç DM ile bildirilecek.", ephemeral=True)

class BasvuruDegerlendir(discord.ui.View):
    def __init__(self, basvuran_id, basvuru_no):
        super().__init__(timeout=None)
        self.basvuran_id = basvuran_id
        self.basvuru_no = basvuru_no
    
    async def _kullaniciyi_bul(self, guild):
        """Kullanıcıyı bul - önce member, sonra fetch"""
        user = guild.get_member(self.basvuran_id)
        if not user:
            try:
                user = await bot.fetch_user(self.basvuran_id)
            except:
                pass
        return user
    
    async def _durum_degistir(self, interaction, yeni_durum):
        """Güvenli durum değişimi"""
        veri = veri_yukle()
        basvuru = None
        
        for b in veri["basvurular"]:
            if b["no"] == self.basvuru_no:
                basvuru = b
                break
        
        if not basvuru:
            return False, "Başvuru bulunamadı!"
        
        eski_durum = basvuru["durum"]
        
        # Geçersiz geçiş kontrolü
        if eski_durum == yeni_durum:
            return False, f"Başvuru zaten **{yeni_durum}** durumunda!"
        
        # İstatistik güncelleme
        if eski_durum == "bekliyor":
            if yeni_durum == "onaylandı":
                veri["istatistik"]["onaylanan"] += 1
            elif yeni_durum == "reddedildi":
                veri["istatistik"]["reddedilen"] += 1
        elif yeni_durum == "bekliyor":
            # Yeniden değerlendirmeye alındı
            if eski_durum == "onaylandı" and veri["istatistik"]["onaylanan"] > 0:
                veri["istatistik"]["onaylanan"] -= 1
            elif eski_durum == "reddedildi" and veri["istatistik"]["reddedilen"] > 0:
                veri["istatistik"]["reddedilen"] -= 1
        
        basvuru["durum"] = yeni_durum
        veri_kaydet(veri)
        return True, None
    
    async def _dm_bildirimi(self, guild, durum, mesaj=None):
        """Kullanıcıya DM bildirimi gönder"""
        user = await self._kullaniciyi_bul(guild)
        if not user:
            return
        
        if durum == "onaylandı":
            embed = discord.Embed(
                title="🎉 Başvurunuz Onaylandı!",
                description=f"**{guild.name}** | **#{self.basvuru_no}** başvurunuz onaylandı!",
                color=0x00FF00
            )
            embed.add_field(name="🌟 Tebrikler!", value="Ekibe hoş geldiniz! Yetkili ekibi sizinle iletişime geçecektir.")
        elif durum == "reddedildi":
            embed = discord.Embed(
                title="❌ Başvurunuz Reddedildi",
                description=f"**{guild.name}** | **#{self.basvuru_no}** başvurunuz şu an için uygun görülmedi.",
                color=0xFF0000
            )
            embed.add_field(name="💭 Üzülmeyin!", value="Başka bir zaman tekrar deneyebilirsiniz!")
        elif durum == "bekliyor":
            embed = discord.Embed(
                title="🔄 Başvurunuz Yeniden Değerlendirmede",
                description=f"**{guild.name}** | **#{self.basvuru_no}** başvurunuz yeniden inceleniyor.",
                color=0xFFA500
            )
        else:
            embed = discord.Embed(
                title=f"📝 Başvuru Durumu: {durum}",
                description=f"**{guild.name}** | **#{self.basvuru_no}**",
                color=0x5865F2
            )
        
        if mesaj:
            embed.add_field(name="💬 Yetkili Yorumu", value=mesaj)
        
        embed.set_footer(text="Kross Sentinel • Başvuru Sistemi")
        await guvenli_dm_gonder(user, embed)
    
    @discord.ui.button(label="✅ Onayla", style=discord.ButtonStyle.green, custom_id="basvuru_onayla")
    async def onayla(self, interaction: discord.Interaction, button: discord.ui.Button):
        basarili, hata = await self._durum_degistir(interaction, "onaylandı")
        
        if not basarili:
            return await interaction.response.send_message(f"❌ {hata}", ephemeral=True)
        
        # Butonları güncelle
        self.children[0].disabled = True  # Onayla
        self.children[1].disabled = True  # Reddet
        # Yorum ve Yeniden Değerlendir açık kalsın
        await interaction.message.edit(view=self)
        
        await self._dm_bildirimi(interaction.guild, "onaylandı")
        await interaction.response.send_message(f"✅ #{self.basvuru_no} onaylandı!")
    
    @discord.ui.button(label="❌ Reddet", style=discord.ButtonStyle.red, custom_id="basvuru_reddet")
    async def reddet(self, interaction: discord.Interaction, button: discord.ui.Button):
        basarili, hata = await self._durum_degistir(interaction, "reddedildi")
        
        if not basarili:
            return await interaction.response.send_message(f"❌ {hata}", ephemeral=True)
        
        # Butonları güncelle
        self.children[0].disabled = True  # Onayla
        self.children[1].disabled = True  # Reddet
        # Yorum ve Yeniden Değerlendir açık kalsın
        await interaction.message.edit(view=self)
        
        await self._dm_bildirimi(interaction.guild, "reddedildi")
        await interaction.response.send_message(f"❌ #{self.basvuru_no} reddedildi!")
    
    @discord.ui.button(label="💬 Yorum", style=discord.ButtonStyle.grey, custom_id="basvuru_yorum")
    async def yorum(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BasvuruYorumModal(self.basvuran_id, self.basvuru_no))
    
    @discord.ui.button(label="🔄 Yeniden Değerlendir", style=discord.ButtonStyle.blurple, custom_id="basvuru_yeniden", emoji="🔄", row=1)
    async def yeniden_degerlendir(self, interaction: discord.Interaction, button: discord.ui.Button):
        basarili, hata = await self._durum_degistir(interaction, "bekliyor")
        
        if not basarili:
            return await interaction.response.send_message(f"❌ {hata}", ephemeral=True)
        
        # Butonları güncelle - Onayla ve Reddet'i tekrar aç
        self.children[0].disabled = False  # Onayla
        self.children[1].disabled = False  # Reddet
        self.children[2].disabled = False  # Yorum
        # Yeniden Değerlendir butonu bir süre kapalı kalsın
        await interaction.message.edit(view=self)
        
        await self._dm_bildirimi(interaction.guild, "bekliyor")
        await interaction.response.send_message(f"🔄 #{self.basvuru_no} yeniden değerlendirmeye alındı!")

class BasvuruYorumModal(discord.ui.Modal, title="💬 Başvuru Yorumu"):
    def __init__(self, basvuran_id, basvuru_no):
        super().__init__()
        self.basvuran_id = basvuran_id
        self.basvuru_no = basvuru_no
    
    yorum = discord.ui.TextInput(
        label="Yorumunuz",
        placeholder="Başvuru hakkında yorum...",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        # Yorumu kaydet
        veri = veri_yukle()
        for b in veri["basvurular"]:
            if b["no"] == self.basvuru_no:
                if "yorumlar" not in b:
                    b["yorumlar"] = []
                b["yorumlar"].append({
                    "yorum": self.yorum.value,
                    "yetkili_id": interaction.user.id,
                    "tarih": datetime.now().isoformat()
                })
                break
        veri_kaydet(veri)
        
        # Kullanıcıya bildir
        guild = interaction.guild
        user = guild.get_member(self.basvuran_id)
        if not user:
            try:
                user = await bot.fetch_user(self.basvuran_id)
            except:
                pass
        
        if user:
            embed = discord.Embed(
                title="💬 Başvurunuza Yorum Geldi!",
                description=f"**{guild.name}** | **#{self.basvuru_no}**",
                color=0x5865F2
            )
            embed.add_field(name="💭 Yetkili Yorumu", value=self.yorum.value)
            await guvenli_dm_gonder(user, embed)
        
        await interaction.response.send_message("✅ Yorum gönderildi!", ephemeral=True)

# -------------------- ÖNERİ SİSTEMİ --------------------
class OneriButon(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="💡 Öneri Gönder", style=discord.ButtonStyle.green, custom_id="oneri_gonder", emoji="💡")
    async def oneri_gonder(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(OneriModal())

class OneriModal(discord.ui.Modal, title="💡 Öneri Formu"):
    oneri = discord.ui.TextInput(
        label="Öneriniz Nedir?",
        placeholder="Sadece bir öneri yazın...",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=1000
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user
        
        log_kanal = get(guild.text_channels, name=ONERI_LOG)
        if not log_kanal:
            return await interaction.response.send_message("❌ `öneriler-log` kanalı bulunamadı!", ephemeral=True)
        
        veri = veri_yukle()
        veri["oneri_sayac"] = veri.get("oneri_sayac", 0) + 1
        oneri_no = veri["oneri_sayac"]
        
        veri["oneriler"].append({
            "no": oneri_no,
            "kullanici_id": member.id,
            "kullanici_adi": member.name,
            "oneri": self.oneri.value,
            "tarih": datetime.now().isoformat(),
            "durum": "bekliyor",
            "yorumlar": []
        })
        veri["istatistik"]["toplam_oneri"] = len(veri["oneriler"])
        veri_kaydet(veri)
        
        embed = discord.Embed(
            title=f"💡 Yeni Öneri #{oneri_no}",
            description=self.oneri.value,
            color=0xFFD700,
            timestamp=datetime.now()
        )
        embed.add_field(name="👤 Gönderen", value=f"{member.mention} ({member.name})", inline=True)
        embed.add_field(name="📊 Durum", value="⏳ Beklemede", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else member.default_avatar.url)
        embed.set_footer(text="Kross Öneri Sistemi")
        
        await log_kanal.send(embed=embed, view=OneriDegerlendir(oneri_no))
        
        dm_embed = discord.Embed(
            title="💡 Öneriniz Alındı!",
            description=f"**{guild.name}** sunucusuna öneriniz iletildi.",
            color=0xFFD700
        )
        dm_embed.add_field(name="📋 Öneri No", value=f"#{oneri_no}")
        dm_embed.set_footer(text="Sonuç DM ile bildirilecek")
        
        await guvenli_dm_gonder(member, dm_embed)
        await interaction.response.send_message("✅ Öneriniz gönderildi!", ephemeral=True)

class OneriDegerlendir(discord.ui.View):
    def __init__(self, oneri_no):
        super().__init__(timeout=None)
        self.oneri_no = oneri_no
    
    async def _kullanici_bul(self, guild, kullanici_id):
        """Kullanıcıyı bul"""
        user = guild.get_member(kullanici_id)
        if not user:
            try:
                user = await bot.fetch_user(kullanici_id)
            except:
                pass
        return user
    
    async def _durum_guncelle(self, interaction, yeni_durum):
        """Öneri durumunu güncelle"""
        veri = veri_yukle()
        oneri = None
        kullanici_id = None
        
        for o in veri["oneriler"]:
            if o["no"] == self.oneri_no:
                oneri = o
                kullanici_id = o["kullanici_id"]
                break
        
        if not oneri:
            return None, "Öneri bulunamadı!"
        
        if oneri["durum"] == yeni_durum:
            return kullanici_id, f"Öneri zaten **{yeni_durum}** durumunda!"
        
        oneri["durum"] = yeni_durum
        veri_kaydet(veri)
        return kullanici_id, None
    
    @discord.ui.button(label="✅ Onayla", style=discord.ButtonStyle.green, custom_id="oneri_onay")
    async def onayla(self, interaction: discord.Interaction, button: discord.ui.Button):
        kullanici_id, hata = await self._durum_guncelle(interaction, "onaylandı")
        
        if hata:
            return await interaction.response.send_message(f"❌ {hata}", ephemeral=True)
        
        button.disabled = True
        self.children[1].disabled = True
        await interaction.message.edit(view=self)
        
        if kullanici_id:
            user = await self._kullanici_bul(interaction.guild, kullanici_id)
            if user:
                embed = discord.Embed(
                    title="✅ Öneriniz Onaylandı!",
                    description=f"**{interaction.guild.name}** | **#{self.oneri_no}** onaylandı!",
                    color=0x00FF00
                )
                embed.add_field(name="🌟 Teşekkürler!", value="Sizin gibi düşünen üyelerimiz olduğu için çok şanslıyız!")
                await guvenli_dm_gonder(user, embed)
        
        await interaction.response.send_message(f"✅ #{self.oneri_no} onaylandı!")
    
    @discord.ui.button(label="❌ Reddet", style=discord.ButtonStyle.red, custom_id="oneri_red")
    async def reddet(self, interaction: discord.Interaction, button: discord.ui.Button):
        kullanici_id, hata = await self._durum_guncelle(interaction, "reddedildi")
        
        if hata:
            return await interaction.response.send_message(f"❌ {hata}", ephemeral=True)
        
        button.disabled = True
        self.children[0].disabled = True
        await interaction.message.edit(view=self)
        
        if kullanici_id:
            user = await self._kullanici_bul(interaction.guild, kullanici_id)
            if user:
                embed = discord.Embed(
                    title="❌ Öneriniz Reddedildi",
                    description=f"**{interaction.guild.name}** | **#{self.oneri_no}** şu an için uygun görülmedi.",
                    color=0xFF0000
                )
                embed.add_field(name="💭 Üzülmeyin!", value="Başka önerilerinizi bekliyoruz!")
                await guvenli_dm_gonder(user, embed)
        
        await interaction.response.send_message(f"❌ #{self.oneri_no} reddedildi!")
    
    @discord.ui.button(label="💬 Yorum", style=discord.ButtonStyle.grey, custom_id="oneri_yorum")
    async def yorum(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(OneriYorumModal(self.oneri_no))

class OneriYorumModal(discord.ui.Modal, title="💬 Öneri Yorumu"):
    def __init__(self, oneri_no):
        super().__init__()
        self.oneri_no = oneri_no
    
    yorum = discord.ui.TextInput(
        label="Yorumunuz",
        placeholder="Öneri hakkında yorum...",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        veri = veri_yukle()
        kullanici_id = None
        
        for o in veri["oneriler"]:
            if o["no"] == self.oneri_no:
                if "yorumlar" not in o:
                    o["yorumlar"] = []
                o["yorumlar"].append({
                    "yorum": self.yorum.value,
                    "yetkili_id": interaction.user.id,
                    "tarih": datetime.now().isoformat()
                })
                kullanici_id = o["kullanici_id"]
                break
        
        veri_kaydet(veri)
        
        if kullanici_id:
            user = interaction.guild.get_member(kullanici_id)
            if not user:
                try:
                    user = await bot.fetch_user(kullanici_id)
                except:
                    pass
            
            if user:
                embed = discord.Embed(
                    title="💬 Önerinize Yorum Geldi!",
                    description=f"**{interaction.guild.name}** | **#{self.oneri_no}**",
                    color=0x5865F2
                )
                embed.add_field(name="💭 Yetkili Yorumu", value=self.yorum.value)
                await guvenli_dm_gonder(user, embed)
        
        await interaction.response.send_message("✅ Yorum gönderildi!", ephemeral=True)

# -------------------- OYLAMA --------------------
@bot.command(name='oylama')
@commands.has_permissions(manage_messages=True)
async def oylama(ctx, sure: int = 0, *, soru: str):
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
    
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("✅")
    await msg.add_reaction("❌")
    await msg.add_reaction("🤷")
    
    if sure > 0:
        await asyncio.sleep(sure * 60)
        
        try:
            msg = await ctx.channel.fetch_message(msg.id)
        except:
            return
        
        evet = hayir = cekimser = 0
        for reaction in msg.reactions:
            if str(reaction.emoji) == "✅":
                evet = reaction.count - 1
            elif str(reaction.emoji) == "❌":
                hayir = reaction.count - 1
            elif str(reaction.emoji) == "🤷":
                cekimser = reaction.count - 1
        
        sonuc_embed = discord.Embed(
            title="🗳️ OYLAMA SONUCU",
            description=soru,
            color=0x00FF00 if evet > hayir else 0xFF0000 if hayir > evet else 0xFFA500,
            timestamp=datetime.now()
        )
        sonuc_embed.add_field(name="✅ Evet", value=str(evet), inline=True)
        sonuc_embed.add_field(name="❌ Hayır", value=str(hayir), inline=True)
        sonuc_embed.add_field(name="🤷 Çekimser", value=str(cekimser), inline=True)
        
        kazanan = "✅ Evet kazandı!" if evet > hayir else "❌ Hayır kazandı!" if hayir > evet else "🤷 Berabere!"
        sonuc_embed.add_field(name="📊 Sonuç", value=kazanan, inline=False)
        
        await ctx.send(embed=sonuc_embed)

# -------------------- İSTATİSTİK --------------------
@bot.command(name='istatistik')
@commands.has_permissions(manage_messages=True)
async def istatistik(ctx):
    veri = veri_yukle()
    ist = veri["istatistik"]
    
    embed = discord.Embed(
        title="📊 SENTINEL İSTATİSTİK",
        color=0x5865F2,
        timestamp=datetime.now()
    )
    embed.add_field(name="📩 Toplam Ticket", value=str(ist.get("toplam_ticket", 0)), inline=True)
    embed.add_field(name="📝 Toplam Başvuru", value=str(ist.get("toplam_basvuru", 0)), inline=True)
    embed.add_field(name="💡 Toplam Öneri", value=str(ist.get("toplam_oneri", 0)), inline=True)
    embed.add_field(name="✅ Onaylanan Başvuru", value=str(ist.get("onaylanan", 0)), inline=True)
    embed.add_field(name="❌ Reddedilen Başvuru", value=str(ist.get("reddedilen", 0)), inline=True)
    
    # Aktif ticket sayısı
    aktif_ticket = len(veri.get("tickets", {}))
    embed.add_field(name="🎫 Aktif Ticket", value=str(aktif_ticket), inline=True)
    
    embed.set_footer(text="Kross Sentinel")
    await ctx.send(embed=embed)

# -------------------- YARDIM --------------------
@bot.command(name='yardim', aliases=['h'])
async def yardim(ctx):
    embed = discord.Embed(
        title="🛡️ KROSS SENTINEL",
        description="Profesyonel Discord Yönetim Asistanı",
        color=0x5865F2,
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="📩 Ticket Sistemi",
        value="`🎫・destek` kanalından buton ile ticket aç\n"
              "🤝 Ticketi Al / ↩️ Vazgeç / ⭐ Puanla & Kapat\n"
              "`.ekle @kullanıcı` `.cikar @kullanıcı` `.kaydet` `.puanlar`",
        inline=False
    )
    
    embed.add_field(
        name="📝 Başvuru Sistemi",
        value="`📝・başvuru` kanalından buton ile başvur\n"
              "✅ Onayla / ❌ Reddet / 💬 Yorum / 🔄 Yeniden Değerlendir\n"
              "Sonuçlar DM ile bildirilir",
        inline=False
    )
    
    embed.add_field(
        name="💡 Öneri Sistemi",
        value="`önerim-var` kanalından buton ile öner\n"
              "Onay/Red/Yorum, DM bildirimi",
        inline=False
    )
    
    embed.add_field(
        name="🗳️ Oylama",
        value="`.oylama <dakika> <soru>`\n"
              "Süre 0 = süresiz",
        inline=False
    )
    
    embed.add_field(
        name="📊 İstatistik",
        value="`.istatistik` `.puanlar @yetkili`",
        inline=False
    )
    
    embed.set_footer(text="Kross Sentinel • Prefix: .")
    await ctx.send(embed=embed)

# -------------------- HATA YAKALAMA --------------------
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Bu komutu kullanmak için yetkiniz yok!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("⚠️ Eksik parametre! `.yardim` yazarak komutları görebilirsiniz.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Geçersiz argüman! Kullanıcıyı etiketleyin veya ID girin.")
    else:
        logger.error(f"Komut hatası: {error}")
        await ctx.send(f"❌ Bir hata oluştu: {error}")

# -------------------- BOT HAZIR --------------------
@bot.event
async def on_ready():
    logger.info(f"🛡️ {bot.user} olarak giriş yapıldı!")
    
    # Persistent view'leri ekle
    bot.add_view(TicketKontrol())
    bot.add_view(BasvuruButon())
    bot.add_view(OneriButon()) 
    
    # Her sunucu için kanalları ayarla
    for guild in bot.guilds:
        logger.info(f"Sunucu kontrol ediliyor: {guild.name} ({guild.id})")
        
        try:
            # Destek kanalı
            destek_kanal = get(guild.text_channels, name=DESTEK_KANALI)
            if destek_kanal:
                # Son mesajı kontrol et, varsa düzenle
                son_mesaj = None
                async for msg in destek_kanal.history(limit=1):
                    if msg.author == bot.user:
                        son_mesaj = msg
                        break
                
                embed = discord.Embed(
                    title="📩 DESTEK TALEBİ",
                    description="Bir sorunla karşılaştıysanız aşağıdaki butona tıklayın.\n\n"
                               "• Yetkililer en kısa sürede ilgilenecektir.\n"
                               "• Gereksiz talep açanlar cezalandırılır.",
                    color=0x00FF00
                )
                embed.set_footer(text="Kross Sentinel • Ticket")
                
                if son_mesaj:
                    await son_mesaj.edit(embed=embed, view=TicketKontrol())
                else:
                    # Eski bot mesajlarını temizle
                    async for msg in destek_kanal.history(limit=10):
                        if msg.author == bot.user:
                            await msg.delete()
                    await destek_kanal.send(embed=embed, view=TicketKontrol())
            
            # Başvuru kanalı
            basvuru_kanal = get(guild.text_channels, name=BASVURU_KANALI)
            if basvuru_kanal:
                son_mesaj = None
                async for msg in basvuru_kanal.history(limit=1):
                    if msg.author == bot.user:
                        son_mesaj = msg
                        break
                
                embed = discord.Embed(
                    title="📝 YETKİLİ BAŞVURUSU",
                    description="Aramıza katılmak ister misiniz?\n\n"
                               "• Dürüst ve detaylı cevaplar verin.\n"
                               "• Sonuç DM ile bildirilecektir.",
                    color=0x5865F2
                )
                embed.set_footer(text="Kross Sentinel • Başvuru")
                
                if son_mesaj:
                    await son_mesaj.edit(embed=embed, view=BasvuruButon())
                else:
                    async for msg in basvuru_kanal.history(limit=10):
                        if msg.author == bot.user:
                            await msg.delete()
                    await basvuru_kanal.send(embed=embed, view=BasvuruButon())
            
            # Öneri kanalı
            oneri_kanal = get(guild.text_channels, name=ONERI_KANALI)
            if oneri_kanal:
                son_mesaj = None
                async for msg in oneri_kanal.history(limit=1):
                    if msg.author == bot.user:
                        son_mesaj = msg
                        break
                
                embed = discord.Embed(
                    title="💡 ÖNERİ SİSTEMİ",
                    description="Sunucumuzu geliştirmek için önerilerinizi bekliyoruz!\n\n"
                               "• Önerileriniz yetkililer tarafından değerlendirilecektir.\n"
                               "• Sonuç DM ile bildirilecektir.",
                    color=0xFFD700
                )
                embed.set_footer(text="Kross Sentinel • Öneri")
                
                if son_mesaj:
                    await son_mesaj.edit(embed=embed, view=OneriButon())
                else:
                    async for msg in oneri_kanal.history(limit=10):
                        if msg.author == bot.user:
                            await msg.delete()
                    await oneri_kanal.send(embed=embed, view=OneriButon())
                    
        except Exception as e:
            logger.error(f"Kanal ayarlama hatası ({guild.name}): {e}")
    
    # Bot durumu
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(bot.guilds)} sunucu | .yardim"
        )
    )
    
    logger.info("✅ Tüm sistemler hazır!")
    logger.info(f"📊 {len(bot.guilds)} sunucuda aktif")

# -------------------- BAŞLAT --------------------
if __name__ == "__main__":
    # Flask'ı arka planda başlat
    Thread(target=run_flask, daemon=True).start()
    
    # Token kontrolü
    TOKEN = os.environ.get('DISCORD_TOKEN') or os.getenv('DISCORD_TOKEN')
    
    if not TOKEN:
        logger.error("❌ DISCORD_TOKEN bulunamadı!")
        logger.error("Render'da Environment Variables kısmına DISCORD_TOKEN ekleyin.")
        exit(1)
    
    logger.info("🛡️ Kross Sentinel başlatılıyor...")
    logger.info("📩 Ticket | 📝 Başvuru | 💡 Öneri | 🗳️ Oylama | ⭐ Puanlama")
    logger.info(f"👑 Özel Roller: {', '.join(OZEL_ROLLER)}")
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        logger.error("❌ Geçersiz token! Discord Developer Portal'dan doğru token'ı kopyalayın.")
    except Exception as e:
        logger.error(f"❌ Bot başlatılamadı: {e}")
