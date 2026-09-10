# Railway ga Baza Import Qilish (Qo'llanma)

## Muammo:
Bot lokal ishlaydi (222 ta guruh bor), lekin Railway da ishlamaydi (0 ta guruh).

Sabab: Baza fayli (`bot_database.db`) GitHub ga yuklanmaydi (xavfsizlik uchun).

## Yechim:

### 1-qadam: Database ni export qilish (allaqachon tayyor)
```bash
cd d:/Vento
python export_db.py
```

Bu `database_export.sql` faylni yaratadi (0.34 MB).

### 2-qadam: Railway ga kirish
1. https://railway.app saytiga kiring
2. Vento bot loyihasini tanlang
3. **"Deployments"** yoki **"Console"** tugmasini bosing
4. **"Terminal"** yoki **"Shell"** oching

### 3-qadam: Database ni Railway ga yuklash

Railway terminalda quyidagi buyruqlarni bajaring:

```bash
# 1. Database faylini yaratish
sqlite3 /tmp/bot_database.db

# 2. Export faylni yuklash (agar database_export.sql ni yuklab bo'lsangiz)
# Agar fayl allaqachon yuklanmagan bo'lsa, uni Railway ga yuklang

# 3. Railway da quyidagilarni bajaring:
sqlite3 /tmp/bot_database.db < database_export.sql
```

### 4-qadam: Railway environment sozlamalari

Railway da **"Variables"** yoki **"Environment"** bo'limiga o'ting va quyidagilarni qo'shing:

```
DATABASE_URL=sqlite:///tmp/bot_database.db
```

Yoki agar Railway PostgreSQL ishlatsa:
```
DATABASE_URL=postgresql://user:password@host:port/database
```

### 5-qadam: Qayta deploy

1. **"Deploy"** tugmasini bosing
2. Bot qayta ishga tushgandan keyin test qiling

## Tekshirish:

Botda "🔍 Guruh qidirish" → "Mafia" deb yozing.
Endi 4 ta guruh topilishi kerak!

## Eslatma:

- `database_export.sql` faylni GitHub GA YUKLAMANG!
- Bu fayl faqat Railway ga yuklash uchun
- Hozircha bu fayl `.gitignore` da, shuning uchun xavfsiz

## Yordam:

Agar muammo bo'lsa, Railway loglarini tekshiring:
- Railway dashboard → Logs
- `[GROUP_SEARCH]` prefiksi bilan loglarni qidiring