import telebot
import time
import json
import os
import threading
import re
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# === CARICA CONFIG ===
try:
    from config import TOKEN, TUO_ID
    bot = telebot.TeleBot(TOKEN)
except:
    print("❌ ERRORE: Crea config.py con TOKEN e TUO_ID!")
    exit()

# === LOG CON OFFUSCAMENTO EMAIL (MODIFICATO) ===
def log(t):
    """Registra i messaggi di log offuscando le email per GDPR"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Offusca le email nei log (es: mario.rossi@gmail.com -> mar***@g***.com)
    def offusca_email(testo):
        # Pattern per riconoscere email
        pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        
        def sostituisci(match):
            email = match.group(0)
            if '@' in email:
                local, dominio = email.split('@', 1)
                # Offusca local (es: mariorossi -> mar***)
                local_offuscato = local[:3] + '***' if len(local) > 3 else local[0] + '***'
                # Offusca dominio (es: gmail.com -> g***.com)
                if '.' in dominio:
                    dominio_nome, dominio_est = dominio.split('.', 1)
                    dominio_offuscato = dominio_nome[:1] + '***.' + dominio_est
                else:
                    dominio_offuscato = dominio[:1] + '***'
                return f"{local_offuscato}@{dominio_offuscato}"
            return email
        
        return re.sub(pattern, sostituisci, testo)
    
    messaggio_offuscato = offusca_email(t)
    print(f"[{timestamp}] {messaggio_offuscato}")
    
    with open("log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {messaggio_offuscato}\n")

# === VARIABILI GLOBALI ===
users = None
ultime_richieste = None
violazioni = None
utenti_bannati = None
accettazioni_regole = None
accettazioni_privacy = None
dati_da_cancellare = None
attesa_solo_like = {}
avvisi_inviati = {}

# === IMPOSTAZIONI GDPR ===
GDPR_MAX_GIORNI = 7
GDPR_CANCELLAZIONE_AUTO = True

# === SALVA/CARICA DATI ===
def salva_dati():
    """Salva TUTTI i dati nel file JSON"""
    dati = {
        "ultime_richieste": ultime_richieste,
        "violazioni": violazioni,
        "bannati": list(utenti_bannati),
        "users": users,
        "accettazioni_regole": accettazioni_regole,
        "accettazioni_privacy": accettazioni_privacy,
        "dati_da_cancellare": dati_da_cancellare,
        "attesa_solo_like": attesa_solo_like,
        "avvisi_inviati": avvisi_inviati
    }
    with open("dati_bot.json", "w", encoding="utf-8") as f:
        json.dump(dati, f, indent=2, default=str)
    log("💾 Dati salvati su disco")

def carica_dati():
    """Carica TUTTI i dati dal file JSON"""
    global ultime_richieste, violazioni, utenti_bannati, users, accettazioni_regole, accettazioni_privacy, dati_da_cancellare, attesa_solo_like, avvisi_inviati
    
    try:
        with open("dati_bot.json", "r", encoding="utf-8") as f:
            dati = json.load(f)
            ultime_richieste = dati.get("ultime_richieste", {})
            violazioni = dati.get("violazioni", {})
            utenti_bannati = set(dati.get("bannati", []))
            users = dati.get("users", {})
            accettazioni_regole = dati.get("accettazioni_regole", {})
            accettazioni_privacy = dati.get("accettazioni_privacy", {})
            dati_da_cancellare = dati.get("dati_da_cancellare", {})
            attesa_solo_like = dati.get("attesa_solo_like", {})
            avvisi_inviati = dati.get("avvisi_inviati", {})
        
        print(f"✅ Dati caricati: {len(users)} utenti, {len(attesa_solo_like)} in attesa")
        
        for user_id in list(dati_da_cancellare.keys()):
            if isinstance(dati_da_cancellare[user_id], str):
                try:
                    dati_da_cancellare[user_id] = datetime.fromisoformat(dati_da_cancellare[user_id])
                except:
                    dati_da_cancellare[user_id] = datetime.now()
        
    except FileNotFoundError:
        print("ℹ️ Nessun file dati trovato, partenza pulita")
        inizializza_dati()
    except Exception as e:
        print(f"⚠️ Errore caricamento dati: {e}")
        print("ℹ️ Partenza con dati vuoti")
        inizializza_dati()
        salva_dati()

def inizializza_dati():
    """Inizializza tutte le variabili dati"""
    global ultime_richieste, violazioni, utenti_bannati, users, accettazioni_regole, accettazioni_privacy, dati_da_cancellare, attesa_solo_like, avvisi_inviati
    ultime_richieste = {}
    violazioni = {}
    utenti_bannati = set()
    users = {}
    accettazioni_regole = {}
    accettazioni_privacy = {}
    dati_da_cancellare = {}
    attesa_solo_like = {}
    avvisi_inviati = {}

# Carica i dati all'avvio
carica_dati()

# === FUNZIONE PER VALIDARE LINK YOUTUBE ===
def is_valido_link_youtube(link):
    """Controlla se il link è un video YouTube valido e NON un canale"""
    
    # Lista di pattern che NON vanno bene (canali, homepage, etc)
    pattern_non_validi = [
        r'youtube\.com/@',           # Link canale
        r'youtube\.com/c/',           # Link canale vecchio stile
        r'youtube\.com/channel/',     # Link canale ID
        r'youtube\.com/user/',        # Link canale user
        r'youtube\.com/feed/',        # Feed
        r'youtube\.com/playlist\?',   # Playlist
        r'youtube\.com/results\?',    # Ricerca
    ]
    
    # Pattern validi (video specifici)
    pattern_validi = [
        r'youtu\.be/[a-zA-Z0-9_-]{11}',                    # youtu.be/ID
        r'youtube\.com/watch\?v=[a-zA-Z0-9_-]{11}',        # youtube.com/watch?v=ID
        r'youtube\.com/shorts/[a-zA-Z0-9_-]{11}',          # shorts
        r'youtube\.com/embed/[a-zA-Z0-9_-]{11}',           # embed
    ]
    
    # Prima controlla se è un link non valido
    for pattern in pattern_non_validi:
        if re.search(pattern, link, re.IGNORECASE):
            return False, "canale"
    
    # Poi controlla se è un link valido
    for pattern in pattern_validi:
        if re.search(pattern, link, re.IGNORECASE):
            return True, "video"
    
    return False, "non_valido"

# === CONTROLLA/CREA FILE RICHIESTE ===
def controlla_file_richieste():
    filename = "richieste.txt"
    
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read()
                size = len(content)
                lines = content.count('\n') + 1
                print(f"✅ File {filename} trovato ({size} bytes, {lines} righe)")
        except Exception as e:
            print(f"⚠️ Errore lettura {filename}: {e}")
            with open(filename, "w", encoding="utf-8") as f:
                f.write("=== RICHIESTE BOT KARAOKE ===\n")
                f.write("="*40 + "\n")
    else:
        print(f"ℹ️ File {filename} non trovato, creo file vuoto")
        with open(filename, "w", encoding="utf-8") as f:
            f.write("=== RICHIESTE BOT KARAOKE ===\n")
            f.write("="*40 + "\n")

controlla_file_richieste()

# === SALVA RICHIESTA ===
def salva_richiesta(user_id, dati, stato="IN ATTESA"):
    with open("richieste.txt", "a", encoding="utf-8") as f:
        f.write(f"\n{datetime.now()} - ID:{user_id}\n")
        f.write(f"User: @{dati.get('username', 'N/A')}\n")
        f.write(f"Tipo: {dati.get('tipo', 'N/A')}\n")
        f.write(f"Link: {dati.get('link', 'N/A')}\n")
        f.write(f"Email: {dati.get('email', 'N/A')}\n")
        f.write(f"Stato: {stato}\n")
        f.write(f"Privacy accettata: {'SI' if user_id in accettazioni_privacy else 'NO'}\n")
        f.write(f"GDPR cancellazione: {dati_da_cancellare.get(user_id, 'Non programmata')}\n")
        f.write("-"*40 + "\n")

# === AGGIORNA STATO RICHIESTA ===
def aggiorna_stato_richiesta(user_id, nuovo_stato, email=""):
    try:
        with open("richieste.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        with open("richieste.txt", "w", encoding="utf-8") as f:
            for i, line in enumerate(lines):
                if f"ID:{user_id}" in line:
                    for j in range(i, min(i+10, len(lines))):
                        if "Stato:" in lines[j]:
                            lines[j] = f"Stato: {nuovo_stato}\n"
                        if email and "Email:" in lines[j]:
                            lines[j] = f"Email: {email}\n"
                f.write(lines[i])
        return True
    except Exception as e:
        log(f"❌ Errore aggiorna_stato_richiesta: {e}")
        return False

# === FUNZIONE DI CANCELLAZIONE AUTOMATICA GDPR (MODIFICATA) ===
def cancella_dati_scaduti():
    """Cancella automaticamente i dati scaduti secondo GDPR, inclusi quelli in richieste.txt"""
    if not GDPR_CANCELLAZIONE_AUTO:
        return 0
    
    cancellati = 0
    now = datetime.now()
    
    user_ids_to_remove = []
    for user_id, user_data in list(users.items()):
        if user_data.get("stato") == 0 and user_data.get("email"):
            if user_id in dati_da_cancellare:
                data_cancellazione = dati_da_cancellare[user_id]
                if isinstance(data_cancellazione, str):
                    try:
                        data_cancellazione = datetime.fromisoformat(data_cancellazione)
                    except:
                        data_cancellazione = now - timedelta(days=GDPR_MAX_GIORNI + 1)
                
                if (now - data_cancellazione).days >= GDPR_MAX_GIORNI:
                    user_ids_to_remove.append(user_id)
            else:
                dati_da_cancellare[user_id] = now
                salva_dati()
    
    for user_id in user_ids_to_remove:
        if user_id in users:
            username = users[user_id].get("username", f"ID_{user_id}")
            
            # === PULIZIA DAL FILE richieste.txt ===
            try:
                with open("richieste.txt", "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                with open("richieste.txt", "w", encoding="utf-8") as f:
                    skip = False
                    for line in lines:
                        if f"ID:{user_id}" in line:
                            skip = True
                            continue
                        if skip and line.startswith("-"*40):
                            skip = False
                            continue
                        if not skip:
                            f.write(line)
                log(f"🧹 GDPR: Rimosse richieste di {username} da richieste.txt")
            except Exception as e:
                log(f"⚠️ Errore pulizia richieste.txt per {username}: {e}")
            
            del users[user_id]
            
            if user_id in accettazioni_regole:
                del accettazioni_regole[user_id]
            if user_id in accettazioni_privacy:
                del accettazioni_privacy[user_id]
            
            if user_id in dati_da_cancellare:
                del dati_da_cancellare[user_id]
            
            if user_id in attesa_solo_like:
                del attesa_solo_like[user_id]
            if user_id in avvisi_inviati:
                del avvisi_inviati[user_id]
            
            cancellati += 1
            log(f"🧹 GDPR AUTO: Dati personali cancellati per @{username} (scaduti {GDPR_MAX_GIORNI} giorni)")
    
    for user_id in list(dati_da_cancellare.keys()):
        if user_id not in users:
            del dati_da_cancellare[user_id]
    
    if cancellati > 0:
        salva_dati()
        log(f"✅ GDPR: Cancellati automaticamente {cancellati} set di dati personali scaduti")
    
    return cancellati

# === PROGRAMMAZIONE CANCELLAZIONE AUTOMATICA GDPR ===
def programma_cancellazione_gdpr():
    """Programma la cancellazione automatica dei dati dopo l'invio"""
    
    cancella_dati_scaduti()
    
    def pulizia_periodica():
        while True:
            time.sleep(86400)
            try:
                count = cancella_dati_scaduti()
                if count > 0:
                    try:
                        bot.send_message(TUO_ID, f"""
🧹 CANCELLAZIONE AUTOMATICA GDPR
⏰ {datetime.now().strftime("%d/%m/%Y %H:%M")}
✅ Cancellati {count} set di dati personali scaduti
📅 Dopo {GDPR_MAX_GIORNI} giorni dalla richiesta
""")
                    except:
                        pass
            except Exception as e:
                log(f"❌ Errore pulizia automatica GDPR: {e}")
    
    thread = threading.Thread(target=pulizia_periodica, daemon=True)
    thread.start()
    log(f"✅ Sistema cancellazione automatica GDPR attivato (ogni 24 ore)")

# === CANCELLA DATI UTENTE (DOPO INVIO) CON PROGRAMMAZIONE ===
def cancella_dati_utente(user_id, programma_cancellazione=True):
    """Cancella TUTTI i dati personali di un utente"""
    
    if user_id not in users:
        return False
    
    username = users[user_id].get("username", f"ID_{user_id}")
    email = users[user_id].get("email", "N/A")
    
    if users[user_id].get("stato") == 0 and email != "N/A":
        if programma_cancellazione:
            dati_da_cancellare[user_id] = datetime.now()
            log(f"📅 GDPR: Programmata cancellazione dati per @{username} tra {GDPR_MAX_GIORNI} giorni")
            
            try:
                messaggio_gdpr = f"""
🔔 INFORMAZIONE GDPR

I tuoi dati personali saranno automaticamente cancellati tra {GDPR_MAX_GIORNI} giorni, in conformità al Regolamento Generale sulla Protezione dei Dati (GDPR).

📅 <b>Data cancellazione programmata:</b> {(datetime.now() + timedelta(days=GDPR_MAX_GIORNI)).strftime("%d/%m/%Y")}

<i>I dati vengono conservati solo per il tempo strettamente necessario all'erogazione del servizio.</i>

Per richiedere la cancellazione immediata, usa /cancelladati
"""
                bot.send_message(user_id, messaggio_gdpr, parse_mode="HTML")
            except:
                pass
            
            salva_dati()
            return "programmata"
    else:
        programma_cancellazione = False
    
    dati_cancellati = []
    
    if user_id in users:
        del users[user_id]
        dati_cancellati.append(f"Account utente")
    
    if user_id in accettazioni_regole:
        del accettazioni_regole[user_id]
        dati_cancellati.append("Accettazione regole")
    
    if user_id in accettazioni_privacy:
        del accettazioni_privacy[user_id]
        dati_cancellati.append("Accettazione privacy")
    
    if user_id in dati_da_cancellare:
        del dati_da_cancellare[user_id]
    
    if user_id in attesa_solo_like:
        del attesa_solo_like[user_id]
        dati_cancellati.append("Lista attesa")
    
    if user_id in avvisi_inviati:
        del avvisi_inviati[user_id]
        dati_cancellati.append("Storico avvisi")
    
    salva_dati()
    
    if dati_cancellati:
        log(f"🧹 Dati cancellati per ID {user_id}: {', '.join(dati_cancellati)}")
        return True
    
    return False

# === CONTROLLA SE È BANNATO ===
def is_bannato(user_id):
    return user_id in utenti_bannati

# === AGGIUNGI VIOLAZIONE ===
def aggiungi_violazione(user_id, username, motivo):
    if user_id not in violazioni:
        violazioni[user_id] = 0
    
    violazioni[user_id] += 1
    conteggio = violazioni[user_id]
    
    log(f"⚠️ VIOLAZIONE: @{username} - {motivo} (Totale: {conteggio}/3)")
    
    if conteggio >= 3:
        utenti_bannati.add(user_id)
        salva_dati()
        
        try:
            messaggio_ban = f"""🚫 SEI STATO BANNATO PERMANENTEMENTE
            
Hai superato il limite di violazioni:
• Violazioni: {conteggio}
• Ultima: {motivo}
            
❌ Il ban è permanente e irreversibile."""
            
            bot.send_message(user_id, messaggio_ban)
            log(f"🚫 BAN PERMANENTE applicato a @{username}")
        except Exception as e:
            log(f"❌ Errore invio messaggio ban: {e}")
        
        try:
            bot.send_message(TUO_ID, f"""
🚨 UTENTE BANNATO

👤 @{username}
🆔 {user_id}
📊 Violazioni: {conteggio}/3
📝 Motivo: {motivo}
⏰ Data: {datetime.now().strftime("%d/%m/%Y %H:%M")}
""")
        except Exception as e:
            log(f"❌ Errore notifica admin ban: {e}")
        
        return True
    return False

# === CONTROLLA SE PUÒ FARE NUOVA RICHIESTA ===
def puo_fare_richiesta(user_id):
    if is_bannato(user_id):
        return False, -1, "BANNATO"
    
    if user_id not in ultime_richieste:
        return True, 0, ""
    
    tempo_trascorso = time.time() - ultime_richieste[user_id]
    ore_trascorse = tempo_trascorso / 3600
    
    if ore_trascorse >= 24:
        return True, 0, ""
    else:
        ore_rimanenti = 24 - ore_trascorse
        return False, ore_rimanenti, "TEMPO"

# === CONTROLLA SE HA ACCETTATO PRIVACY ===
def ha_accettato_privacy(user_id):
    return accettazioni_privacy.get(user_id, False)

# === REGISTRA ACCETTAZIONE PRIVACY ===
def registra_accettazione_privacy(user_id):
    accettazioni_privacy[user_id] = datetime.now().isoformat()
    salva_dati()
    log(f"📝 Privacy accettata da ID {user_id}")

# === FUNZIONE PER CONTROLLARE DATA CANCELLAZIONE ===
def get_data_cancellazione(user_id):
    """Restituisce la data programmata di cancellazione GDPR"""
    if user_id in dati_da_cancellare:
        data_canc = dati_da_cancellare[user_id]
        if isinstance(data_canc, str):
            try:
                data_canc = datetime.fromisoformat(data_canc)
            except:
                data_canc = datetime.now()
        
        data_cancellazione = data_canc + timedelta(days=GDPR_MAX_GIORNI)
        giorni_rimasti = (data_cancellazione - datetime.now()).days
        
        return {
            "programmata": True,
            "data_cancellazione": data_cancellazione,
            "giorni_rimasti": max(0, giorni_rimasti)
        }
    
    return {"programmata": False}

# === SISTEMA AVVISI AUTOMATICI ===
def controlla_attesa_e_invia_avvisi():
    """Controlla ogni ora chi è in attesa e invia promemoria"""
    
    def avvisi_periodici():
        while True:
            time.sleep(3600)
            try:
                now = time.time()
                avvisi_inviati_oggi = 0
                
                for user_id, timestamp in list(attesa_solo_like.items()):
                    ore_attesa = (now - timestamp) / 3600
                    
                    if ore_attesa >= 3 and ore_attesa < 4:
                        if not is_avviso_inviato(user_id, "3h"):
                            invia_promemoria(user_id, ore_attesa, 1)
                            registra_avviso(user_id, "3h")
                            avvisi_inviati_oggi += 1
                    
                    elif ore_attesa >= 6 and ore_attesa < 7:
                        if not is_avviso_inviato(user_id, "6h"):
                            invia_promemoria(user_id, ore_attesa, 2)
                            registra_avviso(user_id, "6h")
                            avvisi_inviati_oggi += 1
                    
                    elif ore_attesa >= 9 and ore_attesa < 10:
                        if not is_avviso_inviato(user_id, "9h"):
                            invia_promemoria(user_id, ore_attesa, 3)
                            registra_avviso(user_id, "9h")
                            avvisi_inviati_oggi += 1
                    
                    elif ore_attesa >= 12:
                        if user_id in attesa_solo_like:
                            del attesa_solo_like[user_id]
                            if user_id in avvisi_inviati:
                                del avvisi_inviati[user_id]
                            log(f"⏰ UTENTE RIMOSSO: ID {user_id} dopo 12 ore di attesa")
                            avvisi_inviati_oggi += 1
                
                if avvisi_inviati_oggi > 0:
                    log(f"📨 AVVISI AUTOMATICI: Inviati {avvisi_inviati_oggi} promemoria")
                    
            except Exception as e:
                log(f"❌ Errore avvisi automatici: {e}")
    
    thread = threading.Thread(target=avvisi_periodici, daemon=True)
    thread.start()
    log("✅ Sistema avvisi automatici attivato (controllo ogni ora)")

def is_avviso_inviato(user_id, tipo_avviso):
    if user_id not in avvisi_inviati:
        return False
    return avvisi_inviati[user_id].get(tipo_avviso, False)

def registra_avviso(user_id, tipo_avviso):
    if user_id not in avvisi_inviati:
        avvisi_inviati[user_id] = {}
    avvisi_inviati[user_id][tipo_avviso] = True
    salva_dati()

def invia_promemoria(user_id, ore_attesa, livello):
    if user_id not in users:
        return False
    
    username = users[user_id].get("username", f"ID_{user_id}")
    tipo_richiesta = users[user_id].get("tipo", "N/A")
    link_originale = users[user_id].get("link", "N/A")
    
    if livello == 1:
        messaggio = f"""⏰ <b>CIAO! SEI ANCORA IN ATTESA?</b>

Sono passate <b>{int(ore_attesa)} ore</b> dalla tua richiesta e ho notato che hai lasciato solo il like.

🎁 <b>COME SBLOCCARE SUBITO LA BASE:</b>
1. Vai sul video: {link_originale}
2. Lascia un COMMENTO
3. Poi scrivimi "fatto!"

💛 Appena lo fai, ti invio la base PRIORITARIAMENTE!"""
    
    elif livello == 2:
        messaggio = f"""⚠️ <b>PROMEMORIA - 6 ORE DI ATTESA</b>

Sono passate <b>6 ore</b> e sei ancora in attesa.

📢 <b>RICORDA:</b>
• Like + Commento = invio IMMEDIATO
• Solo Like = coda LENTA

👉 Il video: {link_originale}"""
    
    else:
        messaggio = f"""🔴 <b>ULTIMO AVVISO - 9 ORE DI ATTESA</b>

Sono {int(ore_attesa)} ore che aspetti.

⚠️ <b>SE NON COMMENTI ENTRO 3 ORE:</b>
• La richiesta verrà ANNULLATA
• Dovrai rifare tutto da capo

👉 {link_originale}"""
    
    try:
        bot.send_message(user_id, messaggio, parse_mode="HTML")
        return True
    except:
        return False

# ====================== COMANDI PUBBLICI ======================

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"ID_{user_id}"
    
    if is_bannato(user_id):
        testo = """🚫 ACCESSO NEGATO - SEI BANNATO
        
Il tuo account è stato bannato permanentemente.
❌ Il ban è irreversibile."""
        bot.reply_to(message, testo)
        log(f"BANNATO tenta accesso: @{username}")
        return
    
    if ha_accettato_privacy(user_id):
        puo, ore_rimaste, tipo = puo_fare_richiesta(user_id)
        
        if puo:
            if user_id not in users:
                users[user_id] = {
                    "stato": 1, 
                    "tipo": "", 
                    "link": "", 
                    "email": "",
                    "username": username
                }
            else:
                users[user_id]["stato"] = 1
                users[user_id]["username"] = username
            salva_dati()
            
            mostra_pulsanti_scelta(message.chat.id)
            log(f"CONTINUA: @{username} già aveva accettato privacy")
            return
        elif tipo == "TEMPO":
            ore_rimaste_int = int(ore_rimaste)
            minuti_rimasti = int((ore_rimaste - ore_rimaste_int) * 60)
            
            testo = f"""⏳ LIMITE RICHIESTE RAGGIUNTO
            
Hai già fatto una richiesta nelle ultime 24 ore.
            
⏰ Tempo rimanente: {ore_rimaste_int} ore e {minuti_rimasti} minuti
            
👉 Usa /status per controllare il tuo stato."""
            
            bot.reply_to(message, testo)
            log(f"LIMITE: @{username} ha già richiesto, {ore_rimaste:.1f} ore rimaste")
            return
    
    start_text = """
<b>🤖 ITALIA KARAOKE BOT</b>

Benvenuto! Con questo bot puoi:
• 🎧 Richiedere nuove devocalizzazioni
• 📺 Scegliere tra le demo già pronte sul canale YouTube

Prima di iniziare, <b>DEVI LEGGERE E ACCETTARE:</b>
• 🛡️ L'informativa sulla privacy (GDPR)

Clicca su "📜 LEGGI E ACCETTA" per continuare.
"""
    
    keyboard = InlineKeyboardMarkup()
    rules_button = InlineKeyboardButton("📜 LEGGI E ACCETTA", callback_data="view_privacy")
    keyboard.add(rules_button)
    
    bot.send_message(message.chat.id, start_text, parse_mode="HTML", reply_markup=keyboard)
    log(f"START: @{username} - Mostrato pulsante iniziale")

# === FUNZIONE PER MOSTRARE PRIVACY SEMPLIFICATA ===
def mostra_privacy_semplice(chat_id, message_id=None):
    testo = f"""
<b>🛡️ INFORMATIVA SULLA PRIVACY</b>

<b>✅ COSA FACCIAMO:</b>
• Ti inviamo la base karaoke via email
• Gestiamo la tua richiesta (24h)
• Ti aiutiamo se hai problemi

<b>🔒 I TUOI DATI SONO SICURI:</b>
• Usiamo crittografia avanzata
• <b>Dati conservati SOLO {GDPR_MAX_GIORNI} giorni</b>
• <b>Cancellati AUTOMATICAMENTE dopo</b>
• Manteniamo solo l'ora (anonima) per limite 24h
• <b>Cancellazione immediata quando vuoi</b> (/cancelladati)

<b>👤 I TUOI DIRITTI:</b>
• Accesso ai tuoi dati
• Correzione se sbagliamo
• <b>Cancellazione totale quando vuoi</b>
• Portabilità dei dati

<b>📊 COSA CONSERVIAMO:</b>
• Nome utente Telegram (anonimo)
• Email (solo per inviarti il file)
• Link YouTube che ci mandi
• Orario della richiesta (per limite 24h)

<b>🚫 COSA NON FACCIAMO MAI:</b>
• Vendere o dare i tuoi dati
• Spammarti con pubblicità
• Condividere con altri
• Conservare più del necessario

<b>Per cancellare i tuoi dati in qualsiasi momento:</b>
Usa il comando /cancelladati

Cliccando "✅ ACCETTO E INIZIO" confermi di aver letto e accetti l'informativa sulla privacy.
"""
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    accept_button = InlineKeyboardButton("✅ ACCETTO E INIZIO", callback_data="accept_privacy")
    keyboard.add(accept_button)
    
    if message_id:
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=testo, parse_mode="HTML", reply_markup=keyboard)
    else:
        bot.send_message(chat_id, testo, parse_mode="HTML", reply_markup=keyboard)

# === FUNZIONE PER MOSTRARE PULSANTI A/B ===
def mostra_pulsanti_scelta(chat_id, message_id=None):
    testo = """✅ <b>Perfetto! Informativa accettata.</b>
    
<b>Scegli il tipo di base:</b>
    
Clicca su uno dei due pulsanti qui sotto:"""
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    button_a = InlineKeyboardButton("🎬 A - DEMO ESISTENTE", callback_data="scelta_A")
    button_b = InlineKeyboardButton("🎵 B - NUOVA DEVOCALIZZAZIONE", callback_data="scelta_B_type")
    
    keyboard.add(button_a, button_b)
    
    if message_id:
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=testo, parse_mode="HTML", reply_markup=keyboard)
    else:
        bot.send_message(chat_id, testo, parse_mode="HTML", reply_markup=keyboard)

# === FUNZIONE PER SCELTA TIPO DEVOCALIZZAZIONE ===
def mostra_scelta_devo_tipo(chat_id, message_id=None):
    testo = """🎵 <b>NUOVA DEVOCALIZZAZIONE - SCEGLI TIPO</b>

<b>✅ VERSIONE COMPLETA (Strumentale Puro)</b>
La voce solista principale è rimossa al 100%. Ideale per sostituirla completamente con la tua.

<b>🎤 VERSIONE CON CORI</b>
Viene rimossa solo la voce solista. I cori di supporto originali restano intatti (se presenti nel brano), per darti un accompagnamento più ricco e "dal vivo".

<u>Seleziona una delle due opzioni principali qui sotto:</u>"""

    keyboard = InlineKeyboardMarkup(row_width=1)
    
    button_completa = InlineKeyboardButton("✅ COMPLETA (solo strumentale)", callback_data="scelta_B_completa")
    button_cori = InlineKeyboardButton("🎤 CON CORI (se disponibili)", callback_data="scelta_B_cori")
    button_avanzate = InlineKeyboardButton("⚙️ OPZIONI AVANZATE", callback_data="opzioni_avanzate")
    button_indietro = InlineKeyboardButton("↩️ TORNA INDIETRO", callback_data="torna_indietro")
    
    keyboard.add(button_completa, button_cori, button_avanzate, button_indietro)
    
    if message_id:
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=testo, parse_mode="HTML", reply_markup=keyboard)
    else:
        bot.send_message(chat_id, testo, parse_mode="HTML", reply_markup=keyboard)

# === FUNZIONE PER OPZIONI AVANZATE ===
def mostra_opzioni_avanzate(chat_id, message_id=None):
    testo = """⚙️ <b>OPZIONI AVANZATE</b>

🎙️ <b>RIMOZIONE SPECIFICA PER GENERE VOCALE</b>
Puoi richiedere la rimozione solo della voce maschile o solo della voce femminile, mantenendo eventuali cori e l'altra voce solista intatta. Perfetto per duetti o per esercitarti su una specifica parte.

🎭 <b>LIVE EDIT (Pulizia Audio Concerti)</b>
Per le registrazioni dal vivo, posso eliminare cori del pubblico, voci parlate, applausi e rumori di fondo, lasciando solo la base musicale, per una esperienza più pulita e professionale.

🎶 <b>MODULAZIONE DI TONALITÀ</b>
Desideri la base in una tonalità diversa? Posso modulare l'intera base (su o giù di semitoni) per adattarla perfettamente alla tua estensione vocale. Indicami semplicemente la tonalità che preferisci!

<u>Nota: Alcune opzioni potrebbero richiedere tempo aggiuntivo di elaborazione.</u>"""

    keyboard = InlineKeyboardMarkup(row_width=1)
    
    button_genere = InlineKeyboardButton("🎙️ RIMOZIONE PER GENERE VOCALE", callback_data="opzione_genere")
    button_live = InlineKeyboardButton("🎭 LIVE EDIT (Audio Concerti)", callback_data="opzione_live")
    button_tonalita = InlineKeyboardButton("🎶 MODULAZIONE TONALITÀ", callback_data="opzione_tonalita")
    button_indietro = InlineKeyboardButton("↩️ TORNA ALLE OPZIONI PRINCIPALI", callback_data="torna_scelta_tipo")
    
    keyboard.add(button_genere, button_live, button_tonalita, button_indietro)
    
    if message_id:
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=testo, parse_mode="HTML", reply_markup=keyboard)
    else:
        bot.send_message(chat_id, testo, parse_mode="HTML", reply_markup=keyboard)

# === GESTIONE CALLBACK ===
@bot.callback_query_handler(func=lambda call: call.data == "view_privacy")
def handle_view_privacy(call):
    mostra_privacy_semplice(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Leggi l'informativa sulla privacy")

@bot.callback_query_handler(func=lambda call: call.data == "accept_privacy")
def handle_accept_privacy(call):
    user_id = call.from_user.id
    username = call.from_user.username or f"ID_{user_id}"
    
    if is_bannato(user_id):
        bot.answer_callback_query(call.id, "❌ Sei bannato permanentemente!", show_alert=True)
        return
    
    puo, ore_rimaste, tipo = puo_fare_richiesta(user_id)
    
    if not puo and tipo == "TEMPO":
        ore_rimaste_int = int(ore_rimaste)
        minuti_rimasti = int((ore_rimaste - ore_rimaste_int) * 60)
        
        messaggio = f"""⏳ LIMITE RICHIESTE RAGGIUNTO
        
Hai già fatto una richiesta nelle ultime 24 ore.
        
⏰ Tempo rimanente: {ore_rimaste_int} ore e {minuti_rimasti} minuti
        
⚠️ Ogni tentativo di bypassare = violazione!
        
📊 Violazioni attuali: {violazioni.get(user_id, 0)}/3"""
        
        bot.answer_callback_query(call.id, "❌ Devi aspettare prima di poter richiedere!", show_alert=True)
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=messaggio, parse_mode="HTML")
        log(f"LIMITE PULSANTE: @{username} ha già richiesto")
        return
    
    registra_accettazione_privacy(user_id)
    
    users[user_id] = {"stato": 1, "tipo": "", "link": "", "email": "", "username": username}
    salva_dati()
    
    bot.answer_callback_query(call.id, "✅ Informativa accettata!")
    mostra_pulsanti_scelta(call.message.chat.id, call.message.message_id)
    
    log(f"ACCETTAZIONE PRIVACY: @{username}")

@bot.callback_query_handler(func=lambda call: call.data in [
    "scelta_A", "scelta_B_type", "scelta_B_completa", "scelta_B_cori",
    "torna_indietro", "opzioni_avanzate", "torna_scelta_tipo",
    "opzione_genere", "opzione_live", "opzione_tonalita"
])
def handle_scelta_AB(call):
    user_id = call.from_user.id
    username = call.from_user.username or f"ID_{user_id}"
    
    if not ha_accettato_privacy(user_id):
        bot.answer_callback_query(call.id, "❌ Devi prima accettare la privacy!", show_alert=True)
        return
    
    if user_id not in users or users[user_id]["stato"] != 1:
        bot.answer_callback_query(call.id, "❌ Errore nello stato. Usa /start", show_alert=True)
        return
    
    if call.data == "torna_indietro":
        bot.answer_callback_query(call.id, "↩️ Torna alla scelta principale")
        mostra_pulsanti_scelta(call.message.chat.id, call.message.message_id)
        return
    
    if call.data == "torna_scelta_tipo":
        bot.answer_callback_query(call.id, "↩️ Torna alle opzioni principali")
        mostra_scelta_devo_tipo(call.message.chat.id, call.message.message_id)
        return
    
    if call.data == "opzioni_avanzate":
        bot.answer_callback_query(call.id, "⚙️ Opzioni avanzate")
        mostra_opzioni_avanzate(call.message.chat.id, call.message.message_id)
        return
    
    if call.data in ["opzione_genere", "opzione_live", "opzione_tonalita"]:
        if call.data == "opzione_genere":
            scelta_utente = "OPZIONE AVANZATA: RIMOZIONE PER GENERE"
            testo_scelta = "🎙️ <b>Hai scelto: RIMOZIONE SPECIFICA PER GENERE VOCALE</b>"
            istruzioni = """
🔗 <b>Invia il link del brano ORIGINALE</b>

✅ <b>Specifica nel tuo messaggio:</b>
• <b>Voce maschile</b> da rimuovere
• <b>Voce femminile</b> da rimuovere
• Entrambe se vuoi solo gli strumenti

⚠️ <i>Il link del video deve essere preso dal canale ufficiale dell'artista</i>
❌ <b>Altrimenti questa richiesta verrà cancellata</b>

📌 <b>Come fare:</b>
1. Cerca il video su YouTube
2. Assicurati sia dal canale UFFICIALE dell'artista
3. Copia il link
4. Incollalo qui seguito da un messaggio con le tue specifiche"""
        
        elif call.data == "opzione_live":
            scelta_utente = "OPZIONE AVANZATA: LIVE EDIT"
            testo_scelta = "🎭 <b>Hai scelto: LIVE EDIT (Pulizia Audio Concerti)</b>"
            istruzioni = """
🔗 <b>Invia il link della registrazione LIVE</b>

✅ <b>Cosa viene fatto:</b>
• Rimozione applausi e cori del pubblico
• Riduzione rumori di fondo
• Pulizia voci parlate/interferenze
• Mantenimento della base musicale

⚠️ <b>IMPORTANTE:</b> Questa opzione è disponibile solo per registrazioni dal vivo di qualità sufficiente.
<i>Il risultato dipende dalla qualità dell'audio originale.</i>

📌 <b>Come fare:</b>
1. Trova il video live su YouTube
2. Assicurati sia una registrazione dal vivo
3. Copia il link
4. Incollalo qui"""
        
        else:
            scelta_utente = "OPZIONE AVANZATA: MODULAZIONE TONALITÀ"
            testo_scelta = "🎶 <b>Hai scelto: MODULAZIONE DI TONALITÀ</b>"
            istruzioni = """
🔗 <b>Invia il link del brano ORIGINALE</b>

✅ <b>Specifica la modulazione desiderata:</b>
• <b>+N</b> per alzare di N semitoni (es: +2)
• <b>-N</b> per abbassare di N semitoni (es: -1)
• <b>Range consentito:</b> da -3 a +3 semitoni

🎵 <b>Esempi:</b>
• "+2" per alzare di 2 semitoni
• "-1" per abbassare di 1 semitono
• "0" per tonalità originale

⚠️ <i>Il link del video deve essere preso dal canale ufficiale dell'artista</i>
❌ <b>Altrimenti questa richiesta verrà cancellata</b>

📌 <b>Come fare:</b>
1. Cerca il video su YouTube
2. Assicurati sia dal canale UFFICIALE dell'artista
3. Copia il link
4. Incollalo qui seguito dal numero di semitoni (es: -2)"""
    
    elif call.data == "scelta_A":
        scelta_utente = "DEMO"
        testo_scelta = "🎬 <b>Hai scelto: DEMO ESISTENTE</b>"
        istruzioni = """
🔗 <b>Invia il link della DEMO che hai trovato nel canale https://www.youtube.com/@ItaliaKaraoke</b>

⚠️ <i>Il link deve essere preso dal nostro canale ufficiale</i>

📌 <b>Come fare:</b>
1. Vai su https://www.youtube.com/@ItaliaKaraoke
2. Trova la demo che ti interessa
3. Copia il link YouTube
4. Incollalo qui"""
    
    elif call.data == "scelta_B_type":
        bot.answer_callback_query(call.id, "🎵 Scegli tipo devocalizzazione")
        mostra_scelta_devo_tipo(call.message.chat.id, call.message.message_id)
        return
    
    elif call.data in ["scelta_B_completa", "scelta_B_cori"]:
        if call.data == "scelta_B_completa":
            scelta_utente = "NUOVA COMPLETA"
            testo_scelta = "🎵 <b>Hai scelto: NUOVA DEVOCALIZZAZIONE COMPLETA</b>"
            istruzioni = """
🔗 <b>Invia il link del brano ORIGINALE</b>

✅ <b>Tipo: COMPLETA (solo strumentale)</b>
• Voce principale: 100% rimossa
• Cori: Mantenuti al 100% (se presenti)
• Strumenti: Mantenuti al 100%
• Ideale per cantare sopra

⚠️ <i>Il link del video deve essere preso dal canale ufficiale dell'artista</i>
❌ <b>Altrimenti questa richiesta verrà cancellata</b>

📌 <b>Come fare:</b>
1. Cerca il video su YouTube
2. Assicurati sia dal canale UFFICIALE dell'artista
3. Copia il link
4. Incollalo qui"""
        else:
            scelta_utente = "NUOVA CON CORI"
            testo_scelta = "🎵 <b>Hai scelto: NUOVA DEVOCALIZZAZIONE CON CORI</b>"
            istruzioni = """
🔗 <b>Invia il link del brano ORIGINALE</b>

✅ <b>Tipo: CON CORI (se disponibili)</b>
• Voce solista: 100% rimossa
• Cori di sottofondo: Mantenuti al 100%
• Strumenti: Mantenuti al 100%
• Perfetto per duetti/cori

⚠️ <b>IMPORTANTE:</b> I cori sono disponibili solo se sono separati nel mix originale.
<i>Se non sono separati, riceverai la versione COMPLETA.</i>

⚠️ <i>Il link del video deve essere preso dal canale ufficiale dell'artista</i>
❌ <b>Altrimenti questa richiesta verrà cancellata</b>

📌 <b>Come fare:</b>
1. Cerca il video su YouTube
2. Assicurati sia dal canale UFFICIALE dell'artista
3. Copia il link
4. Incollalo qui"""
    else:
        return
    
    users[user_id]["tipo"] = scelta_utente
    users[user_id]["stato"] = 2
    users[user_id]["username"] = username
    salva_dati()
    
    bot.answer_callback_query(call.id, f"✅ Selezionato: {scelta_utente}")
    
    testo_completo = f"{testo_scelta}\n\n{istruzioni}"
    
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=testo_completo, parse_mode="HTML")
    
    log(f"SCELTA {scelta_utente}: @{username}")

# === COMANDI PUBBLICI BASE ===
@bot.message_handler(commands=['regole', 'rules'])
def regole(message):
    testo = """📜 <b>REGOLE ITALIA KARAOKE</b>

✅ <b>CONSENTITO:</b>
• Uso domestico/personale
• Ascolto in famiglia
• Prove canore private
• 1 richiesta ogni 24 ore

❌ <b>VIETATO:</b>
• Uso pubblico/commerciale
• Locali, serate, eventi
• Distribuzione/condivisione
• Richieste multiple

⚠️ <b>SANZIONI:</b>
• 1ª violazione: Avviso
• 2ª violazione: Avviso
• 3ª violazione: BAN PERMANENTE

⚠️ <b>IMPORTANTE - RESPONSABILITÀ LEGALE:</b>
Chi utilizza basi karaoke in contesti pubblici o senza autorizzazione 
se ne assume ogni responsabilità legale (SIAE e normative vigenti).
Italia Karaoke non concede licenze e non risponde di abusi o violazioni."""
    
    bot.reply_to(message, testo, parse_mode="HTML")
    log(f"REGOLETTO: @{message.from_user.username or message.from_user.id}")

@bot.message_handler(commands=['privacy', 'gdpr'])
def privacy(message):
    testo = f"""🛡️ <b>INFORMATIVA SULLA PRIVACY</b>

<b>✅ COSA FACCIAMO:</b>
• Ti inviamo la base karaoke via email
• Gestiamo la tua richiesta (24h)
• Ti aiutiamo se hai problemi

<b>🔒 I TUOI DATI SONO SICURI:</b>
• Usiamo crittografia avanzata
• <b>Dati conservati SOLO {GDPR_MAX_GIORNI} giorni</b>
• <b>Cancellati AUTOMATICAMENTE dopo</b>
• Manteniamo solo l'ora (anonima) per limite 24h
• <b>Cancellazione immediata quando vuoi</b> (/cancelladati)

<b>👤 I TUOI DIRITTI:</b>
• Accesso ai tuoi dati
• Correzione se sbagliamo
• <b>Cancellazione totale quando vuoi</b>
• Portabilità dei dati

<b>📊 COSA CONSERVIAMO:</b>
• Nome utente Telegram (anonimo)
• Email (solo per inviarti il file)
• Link YouTube che ci mandi
• Orario della richiesta (per limite 24h)

<b>🚫 COSA NON FACCIAMO MAI:</b>
• Vendere o dare i tuoi dati
• Spammarti con pubblicità
• Condividere con altri
• Conservare più del necessario

<b>Per cancellare i tuoi dati in qualsiasi momento:</b>
Usa il comando /cancelladati"""
    
    bot.reply_to(message, testo, parse_mode="HTML")
    log(f"PRIVACY GDPR: @{message.from_user.username or message.from_user.id}")

@bot.message_handler(commands=['richiesta', 'request', 'howto'])
def richiesta(message):
    testo = """📝 <b>COME RICHIEDERE UNA BASE:</b>

1️⃣ <b>Accetta la privacy</b>
   Usa /start e clicca "📜 LEGGI E ACCETTA"

2️⃣ <b>Scegli il tipo</b>
   A - 🎬 Base demo esistente (da https://www.youtube.com/@ItaliaKaraoke)
   B - 🎵 Nuova devocalizzazione
       • ✅ COMPLETA (solo strumentale)
       • 🎤 CON CORI (se disponibili)
       • ⚙️ OPZIONI AVANZATE
          - 🎙️ Rimozione per genere vocale
          - 🎭 Live Edit (audio concerti)
          - 🎶 Modulazione di tonalità

3️⃣ <b>Invia il link</b>
   🔗 Solo link YouTube validi

4️⃣ <b>Attendi approvazione</b>
   ⏰ 24-48 ore

5️⃣ <b>Invia email</b>
   📧 Email reale per ricevere il file

6️⃣ <b>Ricevi la base!</b>
   🎵 File via Google Drive (scadenza 12h)

⏳ <i>1 richiesta ogni 24 ore</i>
⚠️ <i>3 violazioni = BAN PERMANENTE</i>"""
    
    bot.reply_to(message, testo, parse_mode="HTML")
    log(f"RICHIESTAINFO: @{message.from_user.username or message.from_user.id}")

@bot.message_handler(commands=['aiuto', 'help'])
def aiuto(message):
    testo = """🆘 <b>AIUTO - COMANDI DISPONIBILI:</b>

/start - Avvia il bot (accetta la privacy)
/regole - Leggi le regole d'uso
/privacy - Leggi l'informativa privacy (GDPR)
/richiesta - Come richiedere una base
/status - Verifica il tuo stato e violazioni
/cancelladati - Richiedi cancellazione dati (GDPR)
/aiuto - Questo messaggio

📜 <b>Regola principale:</b> 1 richiesta ogni 24 ore

📞 <b>Problemi o diritti GDPR?</b>
Contatta l'amministratore tramite Telegram.

<i>Comandi admin (solo proprietario):</i>
/lista - Ultime richieste
/mail - Email registrate
/ban ID - Ban utente
/unban ID - Rimuovi ban
/listaban - Lista bannati
/link ID URL - Invia link Drive
/cancella ID - Cancella dati utente (GDPR)
/gdprstatus - Stato cancellazione automatica
/coda - Mostra utenti in attesa per solo like
/invia_prioritario ID URL - Invia subito (like+commento)
/segna_attesa ID - Metti in coda lenta (solo like)
/statattesa - Statistiche della coda
/approva ID - Approva la richiesta e chiede email"""
    
    bot.reply_to(message, testo, parse_mode="HTML")
    log(f"AIUTO: @{message.from_user.username or message.from_user.id}")

@bot.message_handler(commands=['status', 'mystatus', 'mietempo'])
def status_cmd(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"ID_{user_id}"
    
    if is_bannato(user_id):
        testo = """🚫 <b>STATUS: BANNATO PERMANENTEMENTE</b>
        
Il tuo account è stato bannato per 3 violazioni.
❌ Il ban è irreversibile."""
    else:
        violazioni_count = violazioni.get(user_id, 0)
        ha_accettato = ha_accettato_privacy(user_id)
        
        if not ha_accettato:
            testo = """📊 <b>IL TUO STATUS</b>
            
⏳ <i>Non hai ancora accettato la privacy</i>
            
👉 Usa /start per iniziare e accettare."""
        
        elif user_id in ultime_richieste:
            tempo_trascorso = time.time() - ultime_richieste[user_id]
            ore_trascorse = tempo_trascorso / 3600
            
            info_gdpr = get_data_cancellazione(user_id)
            
            if ore_trascorse < 24:
                ore_rimaste = 24 - ore_trascorse
                ore_int = int(ore_rimaste)
                minuti = int((ore_rimaste - ore_int) * 60)
                
                prossima = datetime.fromtimestamp(ultime_richieste[user_id] + 86400).strftime("%d/%m alle %H:%M")
                
                ha_dati_personali = user_id in users and users[user_id].get("email")
                
                if ha_dati_personali:
                    if info_gdpr["programmata"]:
                        stato_privacy = f"📅 <b>Dati in cancellazione automatica:</b> tra {info_gdpr['giorni_rimasti']} giorni"
                    else:
                        stato_privacy = "✅ Dati personali presenti (in attesa invio)"
                else:
                    stato_privacy = "🧹 Dati personali già cancellati (GDPR)"
                
                testo = f"""📊 <b>IL TUO STATUS</b>
                
{stato_privacy}
⏳ <i>Ultima richiesta:</i> {datetime.fromtimestamp(ultime_richieste[user_id]).strftime("%d/%m alle %H:%M")}
⏰ <i>Prossima possibile:</i> {prossima}
🕒 <i>Tempo rimanente:</i> {ore_int}h {minuti}min
⚠️ <i>Violazioni:</i> {violazioni_count}/3
                
📜 <i>Ricorda: 3 violazioni = ban permanente.</i>"""
            else:
                info_gdpr = get_data_cancellazione(user_id)
                ha_dati_personali = user_id in users and users[user_id].get("email")
                
                if ha_dati_personali:
                    if info_gdpr["programmata"]:
                        stato_privacy = f"📅 Dati in cancellazione automatica tra {info_gdpr['giorni_rimasti']} giorni"
                    else:
                        stato_privacy = "✅ Dati personali presenti"
                else:
                    stato_privacy = "🧹 Dati già cancellati (GDPR)"
                
                testo = f"""📊 <b>IL TUO STATUS</b>
                
{stato_privacy}
✅ <i>Puoi fare una nuova richiesta!</i>
⏰ <i>Ultima:</i> più di 24 ore fa
⚠️ <i>Violazioni:</i> {violazioni_count}/3
                
👉 Usa /start per iniziare."""
        else:
            testo = f"""📊 <b>IL TUO STATUS</b>
            
✅ <i>Privacy accettata</i>
🎉 <i>Prima richiesta!</i> Puoi iniziare subito.
⚠️ <i>Violazioni:</i> {violazioni_count}/3
            
👉 Usa /start per iniziare."""
    
    bot.reply_to(message, testo, parse_mode="HTML")
    log(f"STATUS richiesto da @{username}")

# === COMANDO CANCELLADATI POTENZIATO (MODIFICATO) ===
@bot.message_handler(commands=['cancelladati', 'deletemydata', 'gdprdelete'])
def cancelladati(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"ID_{user_id}"
    
    ha_dati = (user_id in users and users[user_id].get("email")) or (user_id in accettazioni_privacy)
    
    if not ha_dati:
        testo = """ℹ️ <b>NESSUN DATO PERSONALE TROVATO</b>

Non sono presenti dati personali da cancellare.
Probabilmente sono già stati cancellati automaticamente secondo le norme GDPR.

Se hai bisogno di ulteriore assistenza, contatta l'amministratore."""
        bot.reply_to(message, testo, parse_mode="HTML")
        return
    
    info_gdpr = get_data_cancellazione(user_id)
    
    if info_gdpr["programmata"]:
        testo = f"""🗑️ <b>CANCELLAZIONE DATI GDPR</b>

I tuoi dati sono già in programma per la cancellazione automatica.

📅 <b>Cancellazione programmata:</b> {info_gdpr['data_cancellazione'].strftime("%d/%m/%Y")}
⏰ <b>Giorni rimanenti:</b> {info_gdpr['giorni_rimasti']}

<b>Vuoi cancellarli IMMEDIATAMENTE?</b>

Scrivi: <code>CANCELLA SUBITO I MIEI DATI</code>

⚠️ <b>Attenzione:</b> La cancellazione è irreversibile!"""
    else:
        testo = """🗑️ <b>RICHIESTO CANCELLAZIONE DATI (GDPR)</b>

Hai richiesto la cancellazione dei tuoi dati personali.

<b>Cosa verrà cancellato ORA:</b>
• Il tuo account dal sistema
• La tua email registrata
• I link che hai inviato
• La storia delle tue richieste

<b>Cosa verrà mantenuto (anonimo):</b>
• Orario ultima richiesta (per limite 24h)
• Eventuali violazioni (per sicurezza)

<b>Conseguenze:</b>
• Dovrai ripartire da zero con /start
• Mantieni il limite 24h se hai fatto richiesta di recente

<b>Per confermare la cancellazione IMMEDIATA:</b>
Scrivi: <code>CANCELLA SUBITO I MIEI DATI</code>

<b>Per annullare:</b>
Ignora questo messaggio"""
    
    bot.reply_to(message, testo, parse_mode="HTML")
    log(f"CANCELLAZIONE DATI richiesta da @{username}")

@bot.message_handler(func=lambda m: m.text and "CANCELLA SUBITO I MIEI DATI" in m.text.upper())
def conferma_cancellazione(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"ID_{user_id}"
    
    # === PULIZIA COMPLETA: JSON + richieste.txt ===
    try:
        # Pulisci da richieste.txt
        with open("richieste.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        with open("richieste.txt", "w", encoding="utf-8") as f:
            skip = False
            for line in lines:
                if f"ID:{user_id}" in line:
                    skip = True
                    continue
                if skip and line.startswith("-"*40):
                    skip = False
                    continue
                if not skip:
                    f.write(line)
        log(f"🧹 GDPR: Rimosse richieste di @{username} da richieste.txt su richiesta diretta")
    except Exception as e:
        log(f"⚠️ Errore pulizia richieste.txt per @{username}: {e}")
    
    # Pulisci dal database
    successo = cancella_dati_utente(user_id, programma_cancellazione=False)
    
    if successo:
        try:
            bot.send_message(TUO_ID, f"""
🗑️ CANCELLAZIONE DATI GDPR (IMMEDIATA)

👤 @{username}
🆔 {user_id}
⏰ {datetime.now().strftime("%d/%m/%Y %H:%M")}

✅ Dati personali cancellati SU RICHIESTA UTENTE (GDPR Art. 17)
✅ Anche da richieste.txt
""")
        except:
            pass
        
        risposta = """✅ <b>CANCELLAZIONE COMPLETATA</b>

Tutti i tuoi dati personali sono stati <b>CANCELLATI IMMEDIATAMENTE</b> dal sistema in conformità al GDPR (Art. 17 - Diritto alla cancellazione).

<b>Cosa è stato cancellato:</b>
• Account e profilo
• Email registrata
• Storico richieste
• Consensi privacy

<b>Mantenuto (anonimo):</b>
• Orario ultima richiesta (per limite 24h)

<b>Se vorrai usare nuovamente il servizio:</b>
Dovrai ripartire da zero con /start

Grazie per aver usato Italia Karaoke! 🎵"""
        
        bot.reply_to(message, risposta, parse_mode="HTML")
        log(f"✅ DATI CANCELLATI IMMEDIATAMENTE per @{username} (GDPR su richiesta + richieste.txt)")
    else:
        bot.reply_to(message, "ℹ️ Non sono stati trovati dati personali da cancellare.")

# ====================== COMANDI ADMIN ======================

@bot.message_handler(func=lambda m: m.text and m.text.startswith('/approva'))
def approva(message):
    """Comando admin per approvare una richiesta e chiedere l'email all'utente"""
    if message.from_user.id != TUO_ID:
        bot.reply_to(message, "❌ Accesso negato. Solo admin.")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ Uso: /approva ID_UTENTE\nEsempio: /approva 123456789")
            return
        
        user_id = int(parts[1])
        
        # Verifica che l'utente esista nel database
        if user_id not in users:
            bot.reply_to(message, f"❌ Utente {user_id} non trovato nel database.")
            return
        
        # Verifica che l'utente non sia già allo stato 3
        if users[user_id]["stato"] == 3:
            bot.reply_to(message, f"ℹ️ L'utente {user_id} è già in attesa di email.")
            return
        
        # Aggiorna lo stato a 3 (in attesa email)
        users[user_id]["stato"] = 3
        salva_dati()
        
        # Aggiorna il file richieste.txt
        aggiorna_stato_richiesta(user_id, "APPROVATA - ATTENDE EMAIL")
        
        # Invia messaggio all'utente per chiedere l'email
        try:
            messaggio_utente = """✅ <b>RICHIESTA APPROVATA!</b>

La tua richiesta è stata approvata dall'amministratore.

📧 <b>Per ricevere la base karaoke, inviami la tua EMAIL:</b>

• Scrivi un indirizzo email valido
• Riceverai il link per il download
• Il file sarà disponibile per 12 ore

⚠️ <b>IMPORTANTE - LEGGI CON ATTENZIONE:</b>

1️⃣ <b>L'IMMAGINE CONTA</b>
   Per favore, invia una email "decente". Non usare email ridicole o offensive.
   Usa un indirizzo serio, preferibilmente Gmail.

2️⃣ <b>COME VERRA' USATA LA TUA EMAIL</b>
   • Solo per inviarti il link di download
   • Conservata per massimo {GDPR_MAX_GIORNI} giorni (GDPR)
   • Cancellata automaticamente dopo
   • MAI condivisa con terzi

3️⃣ <b>EMAIL SCADUTE/NON VALIDE</b>
   Se l'email risulterà non valida o inesistente dopo l'invio:
   • La richiesta verrà ANNULLATA
   • Dovrai rifare tutto da capo
   • Potresti perdere il posto in coda

4️⃣ <b>ESEMPI DI EMAIL CHE NON ACCETTIAMO:</b>
   ❌ batman@email.fake
   ❌ superman@nonvalida.xyz
   ❌ pincopallo@buffa.it
   ❌ indirizzi palesemente falsi

✅ <b>ESEMPI DI EMAIL ACCETTABILI:</b>
   • mariorossi@gmail.com
   • nome.cognome@libero.it
   • la.tua@email.valida.it

📝 <b>Scrivi QUI la tua email:</b>"""
            
            bot.send_message(user_id, messaggio_utente, parse_mode="HTML")
            
            # Notifica all'admin che l'utente è stato contattato
            bot.reply_to(message, f"""✅ <b>RICHIESTA APPROVATA</b>

👤 Utente: @{users[user_id].get('username', f'ID_{user_id}')}
🆔 ID: {user_id}
📨 Stato: In attesa di email

✅ È stato inviato un messaggio all'utente per chiedere l'email.
📋 Quando risponderà, riceverai una notifica.""", parse_mode="HTML")
            
            log(f"✅ APPROVA: Admin ha approvato richiesta per ID {user_id} - In attesa email")
            
        except Exception as e:
            bot.reply_to(message, f"❌ Errore nell'invio del messaggio all'utente: {e}")
            log(f"❌ ERRORE APPROVA: Impossibile contattare ID {user_id}: {e}")
            
    except Exception as e:
        bot.reply_to(message, f"❌ Errore: {e}")
        log(f"❌ Errore comando approva: {e}")

@bot.message_handler(func=lambda m: m.text and m.text.startswith('/cancella'))
def cancella_admin(message):
    if message.from_user.id != TUO_ID:
        bot.reply_to(message, "❌ Accesso negato. Solo admin.")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ Uso: /cancella ID_UTENTE\nEsempio: /cancella 123456789")
            return
        
        user_id = int(parts[1])
        
        successo = cancella_dati_utente(user_id, programma_cancellazione=False)
        
        try:
            bot.send_message(user_id, """🔔 NOTIFICA CANCELLAZIONE DATI

I tuoi dati personali sono stati cancellati dal sistema su richiesta dell'amministratore, in conformità al GDPR.

Se era un errore, puoi ripartire da zero con /start""")
        except:
            pass
        
        if successo:
            risposta = f"""✅ <b>CANCELLAZIONE GDPR COMPLETATA</b>

🆔 Utente: {user_id}
📅 Data: {datetime.now().strftime("%d/%m/%Y %H:%M")}

📋 <b>Dati personali cancellati:</b>
• Account utente (con email)
• Accettazioni privacy

ℹ️ <b>Mantenuti (anonimi):</b>
• Orario ultima richiesta (limite 24h)
• Violazioni (se presenti)

✅ L'utente è stato notificato."""
        else:
            risposta = f"ℹ️ Nessun dato personale trovato per l'utente {user_id} (già cancellati?)"
        
        bot.reply_to(message, risposta, parse_mode="HTML")
        log(f"ADMIN CANCELLA DATI: ID {user_id}")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Errore: {e}")
        log(f"❌ Errore cancellazione admin: {e}")

@bot.message_handler(commands=['mail', 'email', 'mailing'])
def mail(message):
    if message.from_user.id != TUO_ID:
        bot.reply_to(message, "❌ Accesso negato. Solo admin.")
        return
    
    try:
        with open("richieste.txt", "r", encoding="utf-8") as f:
            content = f.read()
        
        if not content:
            bot.reply_to(message, "📭 Nessuna email registrata")
            return
        
        emails = []
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            if "Email:" in line and "N/A" not in line:
                email = line.replace("Email:", "").strip()
                username = "N/A"
                for j in range(max(0, i-5), i):
                    if "User: @" in lines[j]:
                        username = lines[j].replace("User: @", "").strip()
                        break
                
                if email and email not in ["N/A", ""]:
                    emails.append(f"👤 @{username}\n   📧 {email}")
        
        if not emails:
            bot.reply_to(message, "📭 Nessuna email registrata")
            return
        
        totale = len(emails)
        risposta = f"📧 <b>EMAIL REGISTRATE:</b> {totale}\n\n"
        
        ultime_email = emails[-15:]
        
        for i, email in enumerate(ultime_email, 1):
            risposta += f"{i}. {email}\n\n"
        
        if totale > 15:
            risposta += f"\n📊 Mostrate ultime 15 di {totale} email totali."
        
        if len(risposta) > 4000:
            parti = [risposta[i:i+4000] for i in range(0, len(risposta), 4000)]
            for parte in parti:
                bot.send_message(message.chat.id, parte, parse_mode="HTML")
        else:
            bot.reply_to(message, risposta, parse_mode="HTML")
            
        log(f"MAIL: Admin ha visto {totale} email")
            
    except Exception as e:
        bot.reply_to(message, f"❌ Errore: {e}")
        log(f"❌ Errore comando mail: {e}")

@bot.message_handler(commands=['lista'])
def lista(message):
    if message.from_user.id != TUO_ID:
        bot.reply_to(message, "❌ Accesso negato. Solo admin.")
        return
    
    try:
        with open("richieste.txt", "r", encoding="utf-8") as f:
            content = f.read()
        
        if not content:
            bot.reply_to(message, "📭 Nessuna richiesta ancora")
            return
        
        richieste = content.split("-"*40)
        richieste = [r for r in richieste if r.strip()]
        ultime = richieste[-10:]
        
        risposta = "📋 <b>ULTIME 10 RICHIESTE:</b>\n\n"
        
        for i, richiesta in enumerate(reversed(ultime), 1):
            if richiesta.strip():
                lines = richiesta.strip().split('\n')
                if len(lines) >= 3:
                    risposta += f"{i}. {lines[0]}\n"
                    for line in lines[1:6]:
                        risposta += f"   {line}\n"
                    risposta += "\n"
        
        risposta += f"📊 Totale richieste: {len(richieste)}"
        
        if len(risposta) > 4000:
            parti = [risposta[i:i+4000] for i in range(0, len(risposta), 4000)]
            for parte in parti:
                bot.send_message(message.chat.id, parte, parse_mode="HTML")
        else:
            bot.reply_to(message, risposta, parse_mode="HTML")
            
        log(f"LISTA: Admin ha visto {len(richieste)} richieste")
            
    except Exception as e:
        bot.reply_to(message, f"❌ Errore: {e}")
        log(f"❌ Errore lista: {e}")

@bot.message_handler(func=lambda m: m.text and m.text.startswith('/ban'))
def ban_manuale(message):
    if message.from_user.id != TUO_ID:
        bot.reply_to(message, "❌ Accesso negato. Solo admin.")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ Uso: /ban ID_UTENTE [motivo]")
            return
        
        user_id = int(parts[1])
        motivo = " ".join(parts[2:]) if len(parts) > 2 else "Violazione regole (admin)"
        
        utenti_bannati.add(user_id)
        salva_dati()
        
        try:
            bot.send_message(user_id, f"""🚫 SEI STATO BANNATO
            
Motivo: {motivo}
Data: {datetime.now().strftime("%d/%m/%Y %H:%M")}
            
Il ban è permanente.""")
        except:
            pass
        
        bot.reply_to(message, f"✅ Utente {user_id} bannato.\nMotivo: {motivo}")
        log(f"BAN MANUALE: ID {user_id} - Motivo: {motivo}")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Errore: {e}")

@bot.message_handler(func=lambda m: m.text and m.text.startswith('/unban'))
def unban(message):
    if message.from_user.id != TUO_ID:
        bot.reply_to(message, "❌ Accesso negato. Solo admin.")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ Uso: /unban ID_UTENTE")
            return
        
        user_id = int(parts[1])
        
        if user_id in utenti_bannati:
            utenti_bannati.remove(user_id)
            if user_id in violazioni:
                violazioni[user_id] = 0
            salva_dati()
            
            try:
                bot.send_message(user_id, """✅ BAN RIMOSSO
                
Il tuo ban è stato rimosso.
Puoi ora utilizzare nuovamente il bot.""")
            except:
                pass
            
            bot.reply_to(message, f"✅ Ban rimosso per l'utente {user_id}")
            log(f"UNBAN: ID {user_id}")
        else:
            bot.reply_to(message, f"ℹ️ L'utente {user_id} non è bannato")
            
    except Exception as e:
        bot.reply_to(message, f"❌ Errore: {e}")

@bot.message_handler(commands=['listaban', 'banned'])
def listaban(message):
    if message.from_user.id != TUO_ID:
        bot.reply_to(message, "❌ Accesso negato. Solo admin.")
        return
    
    if not utenti_bannati:
        bot.reply_to(message, "📭 Nessun utente bannato")
        return
    
    lista = "🚫 <b>UTENTI BANNATI:</b>\n\n"
    for i, user_id in enumerate(utenti_bannati, 1):
        lista += f"{i}. ID: {user_id}\n"
        lista += f"   Violazioni: {violazioni.get(user_id, 0)}/3\n\n"
    
    bot.reply_to(message, lista, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text and m.text.startswith('/link'))
def invia_link(message):
    if message.from_user.id != TUO_ID:
        bot.reply_to(message, "❌ Accesso negato. Solo admin.")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "❌ Uso: /link ID_UTENTE URL_DRIVE")
            return
        
        user_id = int(parts[1])
        drive_url = parts[2]
        
        if user_id not in users:
            bot.reply_to(message, f"❌ Nessun utente attivo con ID {user_id}")
            return
        
        username = users[user_id]["username"]
        email = users[user_id]["email"]
        
        dati_da_cancellare[user_id] = datetime.now()
        
        if user_id in attesa_solo_like:
            del attesa_solo_like[user_id]
        if user_id in avvisi_inviati:
            del avvisi_inviati[user_id]
        
        messaggio_utente = (
            f"🎵 <b>LA TUA BASE KARAOKE È PRONTA!</b>\n\n"
            
            f"⭐ <b>PRIMA DI SCARICARE, AIUTACI A CRESCERE!</b>\n"
            f"Se il nostro lavoro ti è utile, puoi sostenerci in modo semplice:\n\n"
            f"👍 <b>Metti LIKE al video originale su YouTube</b>\n"
            f"💬 <b>Lascia un COMMENTO</b>\n"
            f"🔔 <b>ISCRIVITI al canale</b> https://www.youtube.com/@ItaliaKaraoke\n\n"
            f"📢 <b>Perché è importante?</b>\n"
            f"• YouTube promuove i video con più interazioni\n"
            f"• Ci aiuta a raggiungere più persone\n"
            f"• Ci motiva a creare nuove basi gratis per te!\n\n"
            f"{'-'*30}\n\n"
            
            f"🔗 <b>Download:</b> {drive_url}\n\n"
            f"⏰ <b>SCADENZA LINK:</b> 12 ore\n"
            f"⚠️ Scarica subito, dopo 12 ore il link si disattiverà!\n\n"
            f"📧 <b>File inviato a:</b> {email}\n\n"
            f"🛡️ <b>INFORMAZIONE GDPR:</b>\n"
            f"I tuoi dati personali (email, link, account) verranno automaticamente cancellati dopo {GDPR_MAX_GIORNI} giorni.\n\n"
            f"📅 <b>Data cancellazione programmata:</b> {(datetime.now() + timedelta(days=GDPR_MAX_GIORNI)).strftime('%d/%m/%Y')}\n\n"
            f"Per cancellazione immediata: /cancelladati\n\n"
            f"{'-'*30}\n\n"
            f"📜 <b>REALTÀ DEL LAVORO DI DEVOCALIZZAZIONE</b>\n\n"
            f"<b>COSA SERVE PER UNA BASE KARAOKE DI QUALITÀ:</b>\n"
            f"• 🕒 2-3 ORE di lavoro specializzato\n"
            f"• 💻 Software professionali (costo annuale)\n"
            f"• 🎧 Hardware di qualità (cuffie, scheda audio)\n"
            f"• 🧠 Competenze tecniche (EQ, mastering, mixing)\n"
            f"• ⚖️ Rispetto scrupoloso delle normative copyright\n\n"
            f"<b>COSA RICEVI:</b>\n"
            f"✅ Base ottimizzata e testata\n"
            f"✅ File pronto all'uso\n"
            f"✅ Supporto tecnico\n"
            f"✅ Garanzia di qualità\n\n"
            f"{'-'*30}\n\n"
            f"<b>SE VUOI SOSTENERCI E CONTRIBUIRE AI COSTI:</b>\n"
            f"👉 https://www.paypal.com/donate/?hosted_button_id=KQSWTSEGKSKPC\n"
            f"<i>(Contributo volontario - non obbligatorio)</i>\n\n"
            f"{'-'*30}\n\n"
            f"💙 Grazie per aver scelto Italia Karaoke!\n"
            f"🎤 Buon divertimento e... cantaci su!"
        )
        
        try:
            bot.send_message(user_id, messaggio_utente, parse_mode="HTML", disable_web_page_preview=False)
            log(f"✅ Link Drive inviato a @{username}")
            
            log(f"📅 GDPR: Programmata cancellazione dati per @{username} tra {GDPR_MAX_GIORNI} giorni")
            
            bot.reply_to(message, f"""✅ Link inviato con successo!
            
👤 A: @{username}
📧 Email: {email}
🔗 Link: {drive_url[:50]}...
⏰ Scadenza: 12 ore
            
✅ Messaggio con:
   • Invito a like/commenti su YouTube
   • Info GDPR
   • Info costi reali
   • Link PayPal contributo volontario
📅 <b>Cancellazione automatica programmata tra {GDPR_MAX_GIORNI} giorni</b>""", parse_mode="HTML")
            
            salva_dati()
            log(f"LINK DRIVE: @{username} -> {drive_url} + cancellazione GDPR programmata")
            
        except Exception as e:
            bot.reply_to(message, f"❌ Errore invio a utente: {e}")
            log(f"❌ Errore invio link a @{username}: {e}")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Errore: {e}")

@bot.message_handler(func=lambda m: m.text and m.text.startswith('/invia_prioritario'))
def invia_prioritario(message):
    if message.from_user.id != TUO_ID:
        bot.reply_to(message, "❌ Accesso negato. Solo admin.")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "❌ Uso: /invia_prioritario ID_UTENTE URL_DRIVE")
            return
        
        user_id = int(parts[1])
        drive_url = parts[2]
        
        # Verifica che l'utente abbia fatto like+commento (tu devi averlo verificato)
        # Qui usiamo lo stesso codice di /link ma con una nota diversa
        message.text = f"/link {user_id} {drive_url}"
        invia_link(message)
        
        if user_id in attesa_solo_like:
            del attesa_solo_like[user_id]
        if user_id in avvisi_inviati:
            del avvisi_inviati[user_id]
        salva_dati()
        
        bot.reply_to(message, f"✅ Inviato PRIORITARIO a ID {user_id} (like+commento verificati)")
        log(f"INVIO PRIORITARIO: ID {user_id} (like+commento)")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Errore: {e}")

@bot.message_handler(func=lambda m: m.text and m.text.startswith('/segna_attesa'))
def segna_attesa(message):
    if message.from_user.id != TUO_ID:
        bot.reply_to(message, "❌ Accesso negato. Solo admin.")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ Uso: /segna_attesa ID_UTENTE")
            return
        
        user_id = int(parts[1])
        
        attesa_solo_like[user_id] = time.time()
        salva_dati()
        
        bot.reply_to(message, f"⏳ Utente {user_id} segnato come 'solo like' - in attesa (riceverà avvisi automatici)")
        log(f"ATTESA: ID {user_id} messo in coda lenta per solo like")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Errore: {e}")

@bot.message_handler(commands=['coda'])
def mostra_coda(message):
    if message.from_user.id != TUO_ID:
        bot.reply_to(message, "❌ Accesso negato. Solo admin.")
        return
    
    if not attesa_solo_like:
        bot.reply_to(message, "📭 Nessun utente in attesa per solo like")
        return
    
    testo = "⏳ <b>UTENTI IN ATTESA (solo like):</b>\n\n"
    
    sorted_users = sorted(attesa_solo_like.items(), key=lambda x: x[1])
    
    for i, (user_id, timestamp) in enumerate(sorted_users, 1):
        attesa_ore = (time.time() - timestamp) / 3600
        
        if user_id in users:
            username = users[user_id].get("username", f"ID_{user_id}")
        else:
            username = f"ID_{user_id}"
        
        # Determina quale avviso è stato già inviato
        avvisi = ""
        if user_id in avvisi_inviati:
            if avvisi_inviati[user_id].get("3h"):
                avvisi += "✅ 3h "
            if avvisi_inviati[user_id].get("6h"):
                avvisi += "✅ 6h "
            if avvisi_inviati[user_id].get("9h"):
                avvisi += "✅ 9h "
        
        testo += f"{i}. 👤 @{username}\n"
        testo += f"   🆔 {user_id}\n"
        testo += f"   ⏰ In attesa da: {attesa_ore:.1f} ore\n"
        if avvisi:
            testo += f"   📨 Avvisi: {avvisi}\n"
        testo += f"   📝 /invia_prioritario {user_id} [link] - invia ora\n\n"
    
    if len(testo) > 4000:
        parti = [testo[i:i+4000] for i in range(0, len(testo), 4000)]
        for parte in parti:
            bot.send_message(message.chat.id, parte, parse_mode="HTML")
    else:
        bot.reply_to(message, testo, parse_mode="HTML")
    
    log(f"CODA: Admin ha visto {len(attesa_solo_like)} utenti in attesa")

@bot.message_handler(commands=['statattesa'])
def stat_attesa(message):
    if message.from_user.id != TUO_ID:
        bot.reply_to(message, "❌ Accesso negato. Solo admin.")
        return
    
    totale_attesa = len(attesa_solo_like)
    if totale_attesa == 0:
        bot.reply_to(message, "📭 Nessuno in attesa")
        return
    
    now = time.time()
    attesa_3h = 0
    attesa_6h = 0
    attesa_9h = 0
    attesa_12h = 0
    
    for timestamp in attesa_solo_like.values():
        ore = (now - timestamp) / 3600
        if ore >= 12:
            attesa_12h += 1
        elif ore >= 9:
            attesa_9h += 1
        elif ore >= 6:
            attesa_6h += 1
        elif ore >= 3:
            attesa_3h += 1
    
    testo = f"""📊 <b>STATISTICHE ATTESA</b>

👥 Totale in coda: {totale_attesa}

⏰ <b>Suddivisione:</b>
• 3-6 ore: {attesa_3h} utenti
• 6-9 ore: {attesa_6h} utenti
• 9-12 ore: {attesa_9h} utenti
• 12+ ore (in rimozione): {attesa_12h} utenti

🔄 Prossimo giro avvisi tra 1 ora"""
    
    bot.reply_to(message, testo, parse_mode="HTML")
    log(f"STAT ATTESA: {totale_attesa} in coda")

@bot.message_handler(commands=['gdprstatus', 'datascaduti'])
def gdpr_status(message):
    if message.from_user.id != TUO_ID:
        bot.reply_to(message, "❌ Accesso negato. Solo admin.")
        return
    
    now = datetime.now()
    totali = len(dati_da_cancellare)
    
    if totali == 0:
        bot.reply_to(message, "ℹ️ Nessun dato in attesa di cancellazione automatica GDPR.")
        return
    
    scaduti = 0
    in_scadenza = []
    
    for user_id, data_inserimento in dati_da_cancellare.items():
        if isinstance(data_inserimento, str):
            try:
                data_inserimento = datetime.fromisoformat(data_inserimento)
            except:
                continue
        
        data_cancellazione = data_inserimento + timedelta(days=GDPR_MAX_GIORNI)
        giorni_rimasti = (data_cancellazione - now).days
        
        if giorni_rimasti <= 0:
            scaduti += 1
        elif giorni_rimasti <= 2:
            username = users.get(user_id, {}).get("username", f"ID_{user_id}")
            in_scadenza.append(f"👤 @{username} (ID: {user_id}) - {giorni_rimasti} giorni")
    
    testo = f"""🛡️ <b>STATO CANCELLAZIONE AUTOMATICA GDPR</b>

📊 <b>Statistiche:</b>
• Totale dati in cancellazione: {totali}
• Dati già scaduti: {scaduti}
• Cancellazione tra: {GDPR_MAX_GIORNI} giorni

<b>⏰ PROSSIME CANCELLAZIONI (≤ 2 giorni):</b>"""
    
    if in_scadenza:
        for item in in_scadenza:
            testo += f"\n• {item}"
    else:
        testo += "\nℹ️ Nessuna cancellazione imminente."
    
    testo += f"\n\n<b>🧹 PULIZIA AUTOMATICA:</b> Ogni 24 ore"
    testo += f"\n<b>🔧 MODIFICA IMPOSTAZIONI GDPR:</b>"
    testo += f"\nSettare GDPR_MAX_GIORNI in codice (attuale: {GDPR_MAX_GIORNI})"
    
    bot.reply_to(message, testo, parse_mode="HTML")
    log(f"GDPR STATUS: {totali} dati in cancellazione, {scaduti} scaduti")

# ====================== GESTIONE FLUSSO UTENTE ======================

@bot.message_handler(func=lambda m: m.text and m.text.upper() in ["ACCETTO", "OK", "SI"])
def accetta_testo(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"ID_{user_id}"
    
    if is_bannato(user_id):
        return
    
    puo, ore_rimaste, tipo = puo_fare_richiesta(user_id)
    
    if not puo:
        if tipo == "TEMPO":
            if user_id in users and users[user_id]["stato"] > 0:
                if aggiungi_violazione(user_id, username, "Riavvio processo durante limite"):
                    return
            
            ore_rimaste_int = int(ore_rimaste)
            minuti_rimasti = int((ore_rimaste - ore_rimaste_int) * 60)
            
            testo = f"""⏳ ATTENZIONE
            
Devi attendere ancora {ore_rimaste_int} ore e {minuti_rimasti} minuti.
⚠️ Ogni ulteriore tentativo = violazione."""
            
            bot.reply_to(message, testo)
            return
        elif tipo == "BANNATO":
            return
    
    registra_accettazione_privacy(user_id)
    
    if user_id not in users:
        users[user_id] = {"stato": 0, "tipo": "", "link": "", "email": "", "username": username}
    
    users[user_id]["stato"] = 1
    users[user_id]["username"] = username
    salva_dati()
    
    mostra_pulsanti_scelta(message.chat.id)
    log(f"ACCETTA via testo: @{username}")

@bot.message_handler(func=lambda m: m.text and m.text.upper() in ["A", "B"])
def scelta_testo(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"ID_{user_id}"
    
    if not ha_accettato_privacy(user_id):
        bot.reply_to(message, "❌ Devi prima accettare la privacy con /start")
        return
    
    if user_id not in users or users[user_id]["stato"] != 1:
        return
    
    scelta_utente = message.text.upper()
    
    if scelta_utente == "A":
        scelta_tipo = "DEMO"
        testo_risposta = """🎬 <b>Hai scelto: DEMO ESISTENTE</b>
        
🔗 <b>Invia il link della DEMO che hai trovato nel canale https://www.youtube.com/@ItaliaKaraoke</b>

⚠️ <i>Il link deve essere preso dal nostro canale ufficiale</i>"""
    else:
        mostra_scelta_devo_tipo(message.chat.id)
        return
    
    users[user_id]["tipo"] = scelta_tipo
    users[user_id]["stato"] = 2
    users[user_id]["username"] = username
    salva_dati()
    
    bot.reply_to(message, testo_risposta, parse_mode="HTML")
    log(f"SCELTA {scelta_tipo} via testo: @{username}")

@bot.message_handler(func=lambda m: m.text and 'youtu' in m.text.lower())
def link(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"ID_{user_id}"
    
    if is_bannato(user_id):
        return
    
    if not ha_accettato_privacy(user_id):
        bot.reply_to(message, "❌ Devi prima accettare la privacy con /start")
        return
    
    if user_id not in users or users[user_id]["stato"] != 2:
        if user_id in ultime_richieste:
            tempo_trascorso = time.time() - ultime_richieste[user_id]
            if tempo_trascorso < 86400:
                aggiungi_violazione(user_id, username, "Invio link durante limite 24h")
                testo = f"""⚠️ VIOLAZIONE REGISTRATA
                
Hai tentato di bypassare il limite.
📊 Violazioni: {violazioni.get(user_id, 0)}/3
                
3 violazioni = ban permanente."""
                bot.reply_to(message, testo)
                return
        return
    
    # === CONTROLLO LINK ===
    link_utente = message.text.strip()
    is_valido, tipo_errore = is_valido_link_youtube(link_utente)
    
    if not is_valido:
        if tipo_errore == "canale":
            testo_errore = """❌ <b>LINK NON VALIDO</b>

Hai inviato il link del <b>CANALE</b>, ma serve il link del <b>VIDEO</b> specifico!

✅ <b>Come fare:</b>
1. Apri il video che vuoi (non il canale)
2. Copia il link dalla barra degli indirizzi
3. Deve essere tipo:
   • https://youtu.be/abc123xyz
   • https://www.youtube.com/watch?v=abc123xyz

❌ NON va bene:
   • youtube.com/@canale
   • youtube.com/c/nomecanale

📌 <b>Riprova con il link del VIDEO!</b>"""
        else:
            testo_errore = """❌ <b>LINK NON VALIDO</b>

Il link che hai inviato non è un link YouTube valido.

✅ <b>Invia un link valido come:</b>
• https://youtu.be/abc123xyz
• https://www.youtube.com/watch?v=abc123xyz

📌 <b>Riprova!</b>"""
        
        bot.reply_to(message, testo_errore, parse_mode="HTML")
        log(f"LINK ERRATO: @{username} - {tipo_errore}")
        return
    
    # Se il link è valido, procedi
    users[user_id]["link"] = link_utente
    users[user_id]["stato"] = 0
    users[user_id]["username"] = username
    salva_dati()
    
    dati = {
        "username": username,
        "tipo": users[user_id]["tipo"],
        "link": users[user_id]["link"],
        "email": ""
    }
    salva_richiesta(user_id, dati, "IN ATTESA APPROVAZIONE")
    
    testo = """✅ <b>Richiesta registrata!</b>
    
📋 <i>Attende approvazione.</i>
⏰ <i>Tempo: 24-48 ore</i>
    
Riceverai un messaggio quando approvata!
    
⚠️ <b>RICORDA:</b> Non altre richieste per 24 ore."""
    
    bot.reply_to(message, testo, parse_mode="HTML")
    
    try:
        notifica = f"""📥 <b>RICHIESTA DA APPROVARE</b>
        
👤 @{username}
🆔 {user_id}
🎵 {dati['tipo']}
🔗 {dati['link']}
📊 Violazioni: {violazioni.get(user_id, 0)}/3
⏰ Privacy accettata: {datetime.fromisoformat(accettazioni_privacy[user_id]).strftime("%d/%m %H:%M")}
        
👉 /approva {user_id}"""
        
        bot.send_message(TUO_ID, notifica, parse_mode="HTML")
        log(f"Notifica admin ID {user_id}")
    except Exception as e:
        log(f"Errore notifica admin: {e}")
    
    log(f"LINK: @{username} - Attende approvazione")

@bot.message_handler(func=lambda m: m.text and "@" in m.text and "." in m.text and " " not in m.text)
def email(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"ID_{user_id}"
    
    if is_bannato(user_id):
        return
    
    if not ha_accettato_privacy(user_id):
        bot.reply_to(message, "❌ Devi prima accettare la privacy con /start")
        return
    
    if user_id not in users or users[user_id]["stato"] != 3:
        if user_id in ultime_richieste:
            tempo_trascorso = time.time() - ultime_richieste[user_id]
            if tempo_trascorso < 86400:
                aggiungi_violazione(user_id, username, "Invio email durante limite 24h")
        return
    
    email_text = message.text.strip()
    users[user_id]["email"] = email_text
    users[user_id]["stato"] = 0
    
    ultime_richieste[user_id] = time.time()
    salva_dati()
    log(f"⏰ Tempo registrato per @{username} alle {datetime.now()}")
    
    log(f"ULTIMA RICHIESTA @{username}: {datetime.now()}")
    
    aggiorna_stato_richiesta(user_id, "EMAIL RICEVUTA - ATTENDE LINK", email_text)
    
    risposta = f"""📧 <b>EMAIL REGISTRATA CON SUCCESSO!</b>
    
La tua email: {email_text}
    
✅ La tua richiesta è in coda. Riceverai la base entro 48 ore.
    
{'='*40}
⭐ <b>ATTENZIONE - LEGGI BENE!</b> ⭐
{'='*40}

<b>Prima di inviarti la base, DEVO vedere:</b>

✅ <b>LIKE</b> sulla demo (obbligatorio)
✅ <b>COMMENTO</b> sulla demo (ALTAMENTE raccomandato)

💡 <b>Perché il commento è così importante?</b>
• Il like da solo non basta per far crescere il canale
• YouTube considera i commenti come "interazione vera"
• Più commenti = più visibilità = più basi gratis per tutti!
• Mi fa capire che sei una persona VERA, non un profilo fantasma

⚠️ <b>Chi lascia SOLO IL LIKE...</b>
... finisce in fondo alla coda. E aspetta MOLTO più a lungo. 
Semplicemente perché il like da solo non mi aiuta abbastanza.

🎁 <b>Chi lascia LIKE + COMMENTO...</b>
... viene servito subito, perché dimostra di aver capito che questo servizio vive della community.

<b>Non serve un commento lungo:</b>
Basta un emoji, un "grazie", un "❤️", qualsiasi cosa!
L'importante è che CI SIA.

{'='*40}
<b>🎯 PROSSIMA RICHIESTA:</b> Tra 24 ore
⚠️ <b>RICORDA:</b> Non altre richieste per 24 ore."""
    
    bot.reply_to(message, risposta, parse_mode="HTML", disable_web_page_preview=False)
    
    try:
        notifica = f"""📧 <b>NUOVA EMAIL DA GESTIRE</b>
        
👤 Utente: @{username}
🆔 ID: {user_id}
📩 Email: {email_text}
🎵 Tipo: {users[user_id]['tipo']}
🔗 Link originale: {users[user_id]['link']}
        
{'='*40}
🔍 <b>VERIFICA LIKE/COMMENTO:</b>
{'='*40}

<b>Prima di inviare il link, controlla:</b>
✅ Like sul video? ________
✅ Commento sul video? ________

💡 <b>Ricorda:</b>
• Solo like = coda lenta
• Like + commento = priorità

<b>Comandi rapidi:</b>
/invia_prioritario {user_id} [drive_link] - Invia SUBITO (like+commento)
/segna_attesa {user_id} - Metti in attesa per solo like
/coda - Vedi tutti in attesa

{'='*40}
📤 <b>PER INVIARE IL LINK DRIVE:</b>
        
/link {user_id} https://tuo.link.drive.qui
        
⏰ Il link scadrà tra 12 ore
        
📝 Il messaggio includerà:
• Link Google Drive (scadenza 12h)
• Info costi reali devocalizzazione
• Link PayPal per contributi volontari
• 📅 Cancellazione automatica dopo {GDPR_MAX_GIORNI} giorni (GDPR)"""
        
        bot.send_message(TUO_ID, notifica, parse_mode="HTML")
        log(f"📧 Notifica email admin per ID {user_id}")
    except Exception as e:
        log(f"Errore notifica email: {e}")
    
    log(f"EMAIL: @{username} -> {email_text}")

# ====================== GESTIONE MESSAGGI PRIVATI ALL'ADMIN ======================

@bot.message_handler(func=lambda m: m.from_user.id == TUO_ID and not m.text.startswith('/'))
def messaggi_privati_admin(message):
    """Gestisce i messaggi privati che l'admin invia al bot"""
    testo = message.text
    log(f"📨 ADMIN ha inviato: {testo}")
    bot.reply_to(message, "✅ Messaggio ricevuto. Usa i comandi / per gestire il bot.")

@bot.message_handler(func=lambda m: True)
def default(message):
    if message.text and message.text.startswith('/'):
        return
    
    user_id = message.from_user.id
    
    # Se è l'admin, gestiscilo separatamente
    if user_id == TUO_ID:
        bot.reply_to(message, "ℹ️ Usa i comandi / per gestire il bot. Es: /aiuto per la lista comandi.")
        return
    
    if not ha_accettato_privacy(user_id):
        testo = "ℹ️ Usa /start per iniziare e accettare la privacy"
    elif user_id not in users:
        testo = "ℹ️ Usa /start per iniziare una nuova richiesta"
    elif users[user_id]["stato"] == 0:
        testo = "ℹ️ Usa /start per iniziare una nuova richiesta"
    elif users[user_id]["stato"] == 1:
        testo = "⚠️ Scegli A o B"
    elif users[user_id]["stato"] == 2:
        testo = "⚠️ Invia link YouTube"
    elif users[user_id]["stato"] == 3:
        testo = "⚠️ Invia la tua email"
    else:
        testo = "ℹ️ Usa /start per nuova richiesta"
    
    bot.reply_to(message, testo)

# === AGGIUNGI QUI LE RIGHE PER RENDER (PRIMA DEL POLLING) ===
import os
import threading

def keep_alive():
    """Mantiene il bot attivo su Render"""
    port = int(os.environ.get('PORT', 5000))
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"https://italia-karaoke-bot.onrender.com/{port}")

# Se siamo su Render, attiva il webhook
if os.environ.get('RENDER'):
    keep_alive()
# === FINE RIGHE PER RENDER ===

# === AVVIO BOT ===
print("="*60)
print("🤖 ITALIA KARAOKE BOT - VERSIONE COMPLETA CON GDPR POTENZIATO")
print("="*60)
print(f"👑 Admin ID: {TUO_ID}")
print(f"🚫 Utenti bannati: {len(utenti_bannati)}")
print(f"👥 Utenti attivi: {len(users)}")
print("="*60)

# Avvia i sistemi automatici
programma_cancellazione_gdpr()
controlla_attesa_e_invia_avvisi()

# === POLLING ===
if __name__ == "__main__":
    try:
        # Se NON siamo su Render, usa il polling normale
        if not os.environ.get('RENDER'):
            bot.polling(none_stop=True, interval=1, timeout=30)
        else:
            # Su Render, rimani in ascolto senza polling
            print("✅ Bot avviato in modalità webhook su Render")
            while True:
                time.sleep(3600)  # Sleep per un'ora, tanto il webhook gestisce tutto
    except KeyboardInterrupt:
        print("\n🛑 Bot fermato manualmente")
        salva_dati()
        print("✅ Dati salvati!")
    except Exception as e:
        print(f"⚠️ Errore nel polling: {e}")
        salva_dati()
        time.sleep(5)