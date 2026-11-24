# 📜 FF Media Bot — Project Rules & Guidelines

Ushbu hujjat foydalanuvchi tomonidan loyiha uchun belgilangan barcha qat'iy talablar, arxitektura qoidalari va kelgusi rejalar jamlanmasidir. Har qanday yangi funksiya yoki o'zgartirish kiritishda ushbu qoidalarga to'liq rioya qilinishi shart!

---

## 1. 🌐 Til va Muloqot Qoidasi
- Botning barcha foydalanuvchi interfeysi (UI), xabarlari, tugmalari, ko'rsatmalari va xatolik matnlari **TO'LIQ INGLIZ TILIDA** bo'lishi shart.

---

## 2. 🚀 Fayl Hajmi va Telegram Premium (4 GB)
- Bot katta media fayllar bilan ishlaydi.
- Foydalanuvchida **Telegram Premium** obunasi mavjud.
- Standart Bot API (50 MB / 2 GB cheklovi) o'rniga bot **MTProto (Hydrogram)** asosida qurilgan bo'lib, **4 GB** gacha bo'lgan katta fayllarni yuklash/yuborish imkoniyatini ta'minlaydi.

---

## 3. 🔄 Yagona Xabar Dinamikasi (Single-Message Navigation)
- **QAT'IY QOIDA:** Menyu yoki funksiyalar tanlanganda **HECH QACHON yangi xabar yuborilmasligi kerak (`reply_text` qilinmasin)**.
- Barcha amallar, so'rovlar, rejim tanlashlar va xabarlar **shu xabarning o'zida (`edit_message_text`)** amalga oshiriladi.
- Har bir ichki menyu va sahifada orqaga qaytuvchi (`⬅️ Back to Menu`) tugmasi bo'lishi shart.
- Asosiy menyuga qaytilganda dastlabki fayl ma'lumotlari (Nomi, hajmi, formati, davomiyligi) qayta tiklanishi shart.

---

## 4. 📁 Media Turlari Bo'yicha Alohida Menyular
Fayl yuborilganda uning turi avtomatik aniqlanadi va unga mos menyu ochiladi:
1. **Audio Menu:** Barcha turdagi audiolarda (`.mp3`, `.m4a`, `.wav`, `.flac`, `.ogg`, `.opus`, `voice note` va h.k.).
2. **Video Menu:** Barcha turdagi videolarda (`.mp4`, `.mkv`, `.avi`, `.mov`, `animation`, `video_note` va h.k.).
3. **File/Document Menu:** Boshqa barcha hujjat, fayl va arxivlarda (`.zip`, `.pdf`, `.iso` va h.k.).

---

## 5. 🎵 Audio Menyusi Funksiyalari
- **✏️ Audio Rename:** Audio fayl nomini o'zgartirish.
- **🔀 Audio Merger:** Bir nechta audiolarni ketma-ket birlashtirish:
  - Foydalanuvchi birinchi audioda `🔀 Audio Merger` tugmasini bosganda, ushbu audio avtomatik ravishda navbatga (Queue 1️⃣) olinadi.
  - Foydalanuvchi keyingi audio fayllarni yuborganida, yangi menyu ochilmaydi (`Single-Message Rule`), balki mavjud menyu xabarining o'zida jonli navbat ro'yxati (1️⃣, 2️⃣, 3️⃣...), umumiy davomiylik va hajm yangilanadi.
  - Kamida 2 ta audio yig'ilganda `[ 🔀 Merge Now (N Tracks) ]` va `[ 🗑️ Reset Queue ]` tugmalari chiqadi.
  - Birlashtirish jarayonida har bir audio ketma-ket yuklab olinadi, FFmpeg orqali barcha format/sample rate/kanallar moslashtirilib (resampled/normalized) xatosiz birlashtiriladi.
  - FFmpeg jarayoni, yuklab olish va yuklash paytida jonli progress bar, ETA, tezlik, `[ 🔄 Refresh ]` va `[ 🚫 Cancel Process ]` ishlaydi.
  - Birlashgan tayyor faylga foydalanuvchining shaxsiy Custom Thumbnaili va aniq hisoblangan `duration` biriktirilib jo'natiladi.
- **✂️ Audio Trimmer:** Bosilganda foydalanuvchidan tanlov so'raydi:
  - `⚡ Fast Copy`: Stream copy rejimida soniyalar ichida sifatni 100% saqlab, qayta kodlamasdan kesish.
  - `🎯 Frame Accuracy`: Kadr aniqligida, millisekundgacha aniq kesish (zarur bo'lsa audio chegaralarini qayta kodlaydi).
- **🏷️ Remove Metadata Title:** Audioning ichidagi `Title` (ID3/MP4 metadata sarlavhasi)ni FFmpeg va Mutagen orqali tozalab, toza audio faylni qaytarish.
- **💻 FFmpeg Command:** Foydalanuvchi o'zi kiritgan FFmpeg argumentlari (masalan, `-af "volume=1.5"`, `-af "atempo=1.25"`, `-b:a 320k` yoki to'liq FFmpeg sintaksisi) asosida audio ustida FFmpeg buyrug'ini xavfsiz va moslashuvchan bajarish, natijani foydalanuvchiga jo'natish.
- **🔍 FFprobe Info:** Audioni yuklab olib, FFprobe orqali uning barcha texnik parametrlarini (kodek, bitrate, sample rate, kanallar, davomiyligi, metadata teglari va formati) chiroyli tahlil qilib xabar ichida (`Single-Message Rule`) foydalanuvchiga taqdim qilish hamda orqaga qaytish imkonini berish.

---

## 5.1. 🎬 Video Menyusi Funksiyalari
1. **✏️ Video Rename:**
   - Foydalanuvchi video nomini chatga yuboradi (masalan, `Movie.mp4` yoki `My_Video`).
   - Kengaytma ko'rsatilmasa asl kengaytma avtomatik saqlanadi.
   - Progress bar orqali yuklab olinadi, qayta nomlanadi va foydalanuvchining maxsus thumbnaili bilan video (yoki document) sifatida jo'natiladi.
2. **🏷️ Metadata Editor:**
   - FFprobe orqali video, audio va subtitr oqimlari (stream) to'liq tahlil qilinadi va barcha mavjud parametrlar (kodek, o'lcham, bitrate, til, sarlavha) yagona menyu xabarida ko'rsatiladi.
   - Barcha streamlarni o'zgartirish imkoniyati:
     - `[ 🎬 Edit Video Title ]`: Videoning umumiy sarlavhasini tahrirlash.
     - Har bir audio oqimi uchun: `[ 🎵 Audio #X (...) ]` (Title va Language code: `Title|Lang` formatida, masalan `AsilMedia|uzb`).
     - Har bir subtitr oqimi uchun: `[ 💬 Sub #X (...) ]` (Title va Language code: `Title|Lang` formatida).
   - **Multi-Edit & In-Memory Draft:** Foydalanuvchi nom kiritganida bot darhol upload QILMAYDI. Kiritilgan yangi qiymat xotiraga (draft) yozilib, foydalanuvchi yana shu Metadata menyusiga qaytariladi. Xabarda o'zgartirilgan oqimlar `✏️ (Modified)` deb ko'rinadi va pastda `[ 💾 Apply & Save Changes ]` tugmasi chiqadi.
   - Foydalanuvchi istasa Audio 1, Audio 2, Subtitle 1 va Video Title — barchasini ketma-ket o'zgartirib chiqishi mumkin.
   - **Yagona FFmpeg Passi:** `[ 💾 Apply & Save Changes ]` tugmasi bosilganda barcha kiritilgan o'zgartirishlar bitta FFmpeg stream-copy (`-c copy`) komandasi orqali videoning sifatini yo'qotmasdan bir necha soniyada bajariladi va Telegramga jo'natiladi.
3. **🗑️ Stream Remover:**
   - Videodagi barcha streamlar (video, audio, subtitle) ffprobe orqali aniqlanadi va tartibli ravishda chiqariladi.
   - Foydalanuvchi xohlagancha streamni (masalan 1, 2, 3 yoki undan ko'p) tanlashi mumkin (multi-select toggle tugmalar orqali).
   - O'chirish uchun tanlangan streamlar ro'yxatda ❌ `[REMOVE]` va tugmada `[🗑️ REMOVE]` belgisi bilan ajralib turadi.
   - Himoya tizimi: Foydalanuvchi barcha streamlarni birdaniga o'chira olmaydi (kamida 1 ta stream qolishi shart).
   - Kamida 1 ta stream tanlanganda `[ 🗑️ Confirm & Remove (N Streams) ]` tasdiqlash tugmasi paydo bo'ladi.
   - Tasdiqlanganda FFmpeg negative mapping (`-map 0 -map -0:X ... -c copy`) orqali videoning sifatini yo'qotmasdan va qayta kodlamasdan bir necha soniyada tanlangan oqimlar olib tashlanadi va yangi video Telegramga yuklanadi.
4. **📤 Stream Extractor:**
   - Videodagi barcha streamlar (video, audio, subtitle) ffprobe orqali to'liq aniqlanadi va ro'yxat ko'rinishida taqdim etiladi.
   - Foydalanuvchi bitta yoki bir nechta streamni tanlashi mumkin (multi-select toggle tugmalar orqali).
   - Tanlangan streamlar 📥 `[EXTRACT]` belgisi bilan ajralib turadi.
   - `[ 📤 Extract Selected (N Streams) ]` tugmasi bosilganda:
     - Har bir tanlangan stream alohida fayl sifatida (FFmpeg stream copy yoki tegishli toza konversiya bilan) ajratib olinadi.
     - **Audio stream:** `.m4a` / `.mp3` / `.opus` / `.flac` formatida Telegramga audio (`send_audio`) sifatida yuboriladi.
     - **Video stream:** ovozsiz video qilib Telegramga video (`send_video`) sifatida yuboriladi.
     - **Subtitle stream:** `.srt` yoki `.ass` formatida Telegramga hujjat (`send_document`) sifatida yuboriladi.
     - Har bir fayl jo'natilishida jonli progress bar, ETA, tezlik va shaxsiy Custom Thumbnail biriktiriladi.
5. **🎵 Merge Audio:**
   - Videoga tashqaridan bir yoki bir nechta audio fayllarni **yangi audio oqimlari (tracks)** sifatida qo'shish (Muxing).
   - Foydalanuvchi video menyusida `[ 🎵 Merge Audio ]` tugmasini bosgach, botga audio fayllarni ketma-ket yuborishi mumkin.
   - Har bir audio yuborilganda yangi menyu ochilmaydi (`Single-Message Rule`), mavjud menyuda navbat ro'yxati (1️⃣, 2️⃣, 3️⃣...) va hajm yangilanib boradi.
   - **Oqimlar tartibi:**
     - 1-yuborilgan audio videoda 1-oqim bo'ladi (`-map 1:a`).
     - 2-yuborilgan audio 2-oqim bo'ladi (`-map 2:a`) va hokazo.
     - Agar videoning o'zida avvaldan audio oqim mavjud bo'lsa, u eng oxirgi oqim sifatida saqlanadi (`-map 0:a?`).
     - **Default Audio Oqim Qoidasi:** Video pleyerlarda (Telegram, VLC va h.k.) videoni ochganda 1-yuborilgan audio avtomatik tarzda birlamchi yangrashi uchun FFmpeg orqali unga default bayrog'i o'rnatiladi (`-disposition:a 0 -disposition:a:0 default`), boshqa oqimlarning default bayroqlari esa tozalanadi.
   - `[ 🔀 Merge Audio Now (N Tracks) ]` tugmasi bosilganda barcha fayllar yuklab olinadi va FFmpeg stream copy (`-c copy`) orqali sifatini 100% original saqlab tezkorlik bilan birlashtiriladi hamda Telegramga yuklanadi.
6. **✂️ Video Trimmer:**
   - Audio Trimmer logikasi asosida 100% moslangan.
   - Foydalanuvchi `[ ✂️ Video Trimmer ]` tugmasini bosganda rejim tanlash ko'rsatiladi:
     - `⚡ Fast Copy`: Stream copy rejimida soniyalar ichida sifatni 100% original saqlab, qayta kodlamasdan kesish.
     - `🎯 Frame Accuracy`: Kadr aniqligida, millisekundgacha aniq kesish (video chegaralari qayta kodlanadi).
   - Foydalanuvchi boshlanish va tugash vaqtini kiritadi (`00:15 - 01:45` yoki `01:30 to 03:00` yoki `15 - 90`).
   - Jonli FFmpeg progress bar, ETA, tezlik ko'rsatiladi va kesilgan video Custom Thumbnail bilan Telegramga yuklanadi.
7. **🔀 Video Merger:**
   - Bir nechta videolarni faqat **Fast Copy** (`-c copy`) orqali birlashtirish.
   - Foydalanuvchi video yuborib `[ 🔀 Video Merger ]` ni bosgach, navbatdagi videolarni ketma-ket yuborishi mumkin (`Single-Message Rule`).
   - Kamida 2 ta video yig'ilganda `[ 🔀 Merge Now (N Videos) ]` tugmasi chiqadi.
   - FFmpeg Concat Demuxer (`-f concat -safe 0 -c copy -avoid_negative_ts make_zero -fflags +genpts`) orqali videolarni qayta kodlamasdan bir necha soniyada birlashtiradi.
8. **💬 Subtitle Merger:**
   - Videoga yangi subtitr fayl(lar)ni (`.srt`, `.ass`, `.vtt`, `.ssa`, `.sub`) yangi oqim(lar) sifatida qo'shish.
   - Mantiqan `5. Merge Audio` bilan 100% bir xil ishlaydi:
     - Foydalanuvchi video yuboradi va `[ 💬 Subtitle Merger ]` tugmasini bosadi.
     - So'ngra bitta yoki ketma-ket bir nechta subtitr faylini chatga yuboradi (`Single-Message Rule` bo'yicha menyu xabarining o'zida jonli navbat ro'yxati yangilanadi).
     - Yangi qo'shilgan subtitrlar videoning birlamchi subtitr oqimlari sifatida biriktiriladi (`-map 1:0`, `-map 2:0`...). Har bir subtitrga uning fayl nomidan sarlavha (title) metadatasi o'rnatiladi.
     - Asl videodagi mavjud subtitrlar saqlanadi (`-map 0:s?`).
     - FFmpeg stream copy (`-c copy` yoki MP4 uchun `-c:s mov_text`, zarur bo'lsa sifat yo'qotmasdan `.mkv` konteyneriga) orqali soniyalar ichida sifatni 100% original saqlab tezkorlik bilan birlashtiriladi va Custom Thumbnail bilan Telegramga yuklanadi.
9. **💻 FFmpeg Command:**
   - Audio menyusidagi FFmpeg command kabi 100% bir xil ishlaydi.
   - Foydalanuvchi o'zi kiritgan FFmpeg video parametrlari (masalan, `-vf "scale=1280:720"`, `-c:v libx264 -crf 23`, `-an`, `-vf "setpts=0.5*PTS"`) asosida jonli progress tracker bilan ishlov beriladi va natija Telegramga yuklanadi.
10. **🔍 FFprobe Info:**
   - Audio menyusidagi FFprobe kabi ishlaydi, faqat **video fayl haqida to'liq va batafsil texnik tahlil** taqdim etadi:
     - Fayl hajmi, davomiyligi, umumiy bitrate, konteyner formati.
     - Video stream(lar): Kodek, profil, o'lcham (resolution + aspect ratio), kadrlar chastotasi (fps), pixel format, bitrate.
     - Audio stream(lar): Kodek, kanallar va layout, sample rate, bitrate, til va sarlavha.
     - Subtitle stream(lar): Kodek, til va sarlavha.
     - Metadata teglari (title, encoder, creation_time va h.k.).
   - Shuningdek, xabar ichida orqaga qaytish (`[ ⬅️ Back to Video Menu ]`) tugmasi mavjud.

---

## 6. ❌ Xabarlarni O'chirish (Close Menu)
- **`❌ Close Menu`** tugmasi bosilganda:
  - Botning menyu xabari;
  - Foydalanuvchi yuborgan asl media xabari (audio, video, file);
  **ikkalasi ham chatdan to'liq o'chirilishi shart**.

---

## 7. ⏱️ Yuklash / Yuklab Olish Progress Tracker
- Katta media fayllarni yuklab olish (Download) va Telegramga yuklash (Upload) jarayonida foydalanuvchiga jonli progress ko'rsatiladi:
  - `Progress Bar` (foiz ko'rsatkichi bilan)
  - **Yuklab olayotganda:** `• Downloaded: current / total`
  - **Yuklayotganda (Upload):** `• Uploaded: current / total`
  - `Speed` (haqiqiy internet tezligi: MB/s yoki KB/s)
  - `ETA` (jarayon tugashiga qolgan vaqt)
  - `Elapsed` (boshlangandan beri o'tgan vaqt)
- **QAT'IY VAQT QOIDASI:** Xabar Telegram cheklovlariga (FloodWait) tushmaslik uchun avtomatik ravishda **aniq har 8 soniyada** (va jarayon 100% tugaganda) yangilanib turishi shart.
- **🔄 Refresh Tugmasi:** Xabar ostida `[ 🔄 Refresh ]` tugmasi bo'ladi. Foydalanuvchi 8 soniyalik intervalni kutmasdan, aynan shu daqiqadagi ko'rsatkichlarni bir zumda yangilab olishi mumkin.
- **🚫 Cancel Process Tugmasi:** Yuklab olish va yuklash jarayonida xabar ostida doimo `[ 🚫 Cancel Process ]` tugmasi bo'ladi. Foydalanuvchi ushbu tugmani bosgan paytda yuklash/yuklab olish darhol (`stop_transmission`) to'xtatiladi, vaqtinchalik fayllar o'chiriladi va xabar bekor qilinganlik holatiga o'tadi.
- **⚙️ FFmpeg Jarayoni Progress Tracker:** Media fayllar ustida FFmpeg amallari (kesish, maxsus buyruq bajarish va h.k.) bajarilayotganda ham yuklab olish/yuklash kabi jonli progress ko'rsatiladi:
  - `Progress Bar` (foiz bilan)
  - `• Processed: current / total` (ishlangan vaqt / kutilayotgan davomiylik)
  - `• Speed: ...x` (FFmpeg ishlov berish tezligi)
  - `• ETA` va `• Elapsed` vaqtlari
  - `[ 🔄 Refresh ]` va `[ 🚫 Cancel Process ]` tugmalari (Cancel bosilganda FFmpeg jarayoni bir zumda o'ldiriladi).
- **🎵 Audio Duration Qoidasi:** Telegramga qayta ishlangan audio yuborilganda, uning aniq davomiyligi `ffprobe` orqali olinib `send_audio(..., duration=out_duration)` orqali Telegramga uzatilishi shart (aks holda Telegram pleerida `00:00` ko'rinadi).

---

## 8. 🖼️ Custom Thumbnail (Muqova Rasmi)
- Foydalanuvchi botga rasm (Photo) yuborganida, bot ushbu rasmni uning shaxsiy Custom Thumbnaili sifatida saqlab oladi (`thumbnails/{user_id}.jpg`).
- Telegram talablariga moslash uchun rasm FFmpeg yordamida avtomatik ravishda JPEG formatiga va maksimal `320x320` o'lchamga keltiriladi.
- Ushbu thumbnail keyingi barcha chiquvchi media fayllarga (Audio, Video, Document) avtomatik biriktiriladi (`thumb=...`).
- **`/showthumb`:** Foydalanuvchining joriy saqlangan thumbnailini ko'rsatish.
- **`/delthumb`:** Saqlangan thumbnailni o'chirish.

---

## 9. 💻 Tizim va Texnik Talablar
- **Python versiyasi:** Python 3.14+ (Asyncio event loop initsializatsiyasi moslashtirilgan).
- **Framework:** `Hydrogram` (Pyrogram v2 ning zamonaviy, qo'llab-quvvatlanuvchi forki).
- **Tezlik & Kriptografiya:** `PyCryptodome` apparat darajasidagi AES-NI tezlatgichi orqali MTProto AES-CTR va AES-IGE algoritmlari `speedups.py` yordamida tezlashtirilgan (~470 barobar tezroq shifrlash/ochish).
- **Parallel uzatish:** `max_concurrent_transmissions=8` va `workers=16` bilan fayllar ko'p oqimli rejimda yuklanadi.
- **Audio & Media:** `mutagen`, `ffmpeg`.
- **Jarayonni to'xtatish:** Windows konsollarida (PowerShell/CMD) **Ctrl+C** bosilganda bot darhol toza to'xtashi uchun signal handlerlar (`SIGINT`, `SIGBREAK`) o'rnatilgan.

---

## 10. ⚙️ Bot Sozlamalari (/settings)
- **`/settings`:** Foydalanuvchi chiquvchi media fayllar formatini (Audio/Video yoki File/Document) sozlashi mumkin bo'lgan menyu.
- **Tugmalar mantig'i:**
  - Dastlab 2 ta asosiy tugma turadi:
    - `Upload as Audio`
    - `Upload as Video`
  - `Upload as Audio` bosilganda `Upload as File` ko'rinishiga o'tadi (audio fayllar Telegram Document ko'rinishida yuboriladi).
  - `Upload as Video` bosilganda `Upload as File` ko'rinishiga o'tadi (video fayllar Telegram Document ko'rinishida yuboriladi).
  - `Upload as File` bosilganda esa mos ravishda yana `Upload as Audio` va `Upload as Video` ko'rinishiga qaytadi.
- **Saqlash:** Sozlamalar SQLite (`user_settings.db`) bazasida doimiy saqlanadi va bot qayta yoqilganda ham o'z kuchini yo'qotmaydi.
- **Yagona Xabar Dinamikasi (Single-Message Rule):** Tugmalar bosilganda xabar joyida yangilanadi (`edit_message_text`) va menyuni yopish uchun `[ ❌ Close ]` tugmasi mavjud.
