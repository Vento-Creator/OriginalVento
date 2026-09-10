# To'g'ridan-to'g'ri Railway ga Deploy (GitOrasiz)

## Eng yaxshi usul - Railway CLI orqali

### 1-qadam: Railway CLI ni o'rnatish

```bash
# Windows uchun (PowerShell yoki CMD):
npm install -g @railway/cli

# Yoki pip orqali:
pip install railway-cli
```

### 2-qadam: Railway ga kirish

```bash
railway login
```

Bu sizni browserda Railway saytiga yo'naltiradi, kirishni tasdiqlang.

### 3-qadam: Loyihani Railway ga ulash

```bash
cd d:/Vento
railway init
```

Quyidagilarni tanlang:
- "Create new project" → "Empty Project"
- Project nomi: `vento-bot`

### 4-qadam: Database ni tayyorlash

```bash
# Database faylini tayyorlash (allaqachon tayyor)
python export_db.py
```

### 5-qadam: Railway ga deploy qilish

```bash
# Barcha fayllarni Railway ga yuklash
railway up
```

Bu quyidagilarni yuklaydi:
- ✅ Barcha Python fayllar
- ✅ Database (agar to'g'ri sozlangan bo'lsa)
- ✅ requirements.txt
- ❌ Session fayllar (gitignore da)
- ❌ Config.json (gitignore da, xavfsiz)

### 6-qadam: Environment o'zgaruvchilarni sozlash

Railway dashboardda:
1. **"Variables"** bo'limiga o'ting
2. Quyidagilarni qo'shing:

```
API_ID=<your_api_id>
API_HASH=<your_api_hash>
BOT_TOKEN=<your_bot_token>
SUPER_ADMIN_ID=<owner_telegram_id>
SECOND_ADMIN_ID=<second_admin_telegram_id>
DATABASE_URL=sqlite:///tmp/bot_database.db
```

### 7-qadam: Database ni import qilish

Railway dashboard → **"Deployments"** → **"View Logs"** yoki **"Console"**

Console da quyidagini bajaring:
```bash
# Database ni yuklash
sqlite3 /tmp/bot_database.db < database_export.sql
```

### 8-qadam: Qayta deploy

```bash
railway up
```

Yoki Railway dashboardda **"Deploy"** tugmasini bosing.

---

## ALTERNATIVA: Railway Dashboard orqali (eng oson)

Agar CLI ishlamasa:

1. **Railway dashboard** ga kiring
2. **"New Project"** → **"Deploy from GitHub"**
3. GitHub repo ni ulang
4. **"Settings"** → **"Build"** → **"Source"** → **"GitHub"**
5. **"Deploy"** tugmasini bosing

**LEKIN** bu usulda database ni alohida import qilish kerak.

---

## YANGI USUL: Railway Volume (Tavsiya qilinadi)

Railway da **Volume** yaratib, database ni doimiy saqlash:

1. Railway dashboard → **"Volumes"** → **"New Volume"**
2. Volume nomi: `bot-data`
3. Mount path: `/app/data`
4. So'ng environment ga qo'shing:
   ```
   DATABASE_URL=sqlite:///app/data/bot_database.db
   ```

Bu usul database ni doimiy saqlaydi, deploy qilganda ham yo'qolmaydi.

---

## Tekshirish:

1. Railway logs ni oching
2. `[GROUP_SEARCH]` loglarni qidiring
3. Botda "Mafia" deb qidiring
4. 4 ta guruh topilishi kerak!

## Afzalliklar:

✅ GitHub ga noma'lum ma'lumotlar ketmaydi
✅ Bitta buyruqda deploy: `railway up`
✅ Database avtomatik ravishda saqlanadi
✅ Session va tokenlar xavfsiz