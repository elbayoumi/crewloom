# Specialist architecture reference

Source-derived reference; current public scope and tool support are defined in the English guide and tool catalog.

# 🏛️ معمارية الصوت والتعليق العصبي (Audio Engineering Architecture)

## Voice Synthesis, Audio Mastering & Social Media Standards

تحدد هذه المعمارية المعايير الهندسية لإنتاج الصوت في Crewloom:

### 1. معايير الصوت للمنصات (Social Audio Standards)
- **مستوى الصوت المتكامل (Integrated Loudness):** `-14 LUFS` (مطابق لخوارزميات ضغط تيك توك، إنستغرام، ويوتيوب).
- **أقصى قمة حقيقية (True Peak):** `-1.0 dBTP` لمنع حدوث التشويه (Distortion) بعد ضغط الـ Codec.
- **معدل العينات (Sample Rate):** `44.1 kHz` أو `48.0 kHz`، 16-bit أو 24-bit Stereo.
- **صيغة الإخراج الأساسية:** MP3 عالي الجودة (192-320 kbps) أو WAV خام للمونتاج المتقدم.

### 2. مكتبة الأصوات العصبية المعتمدة (Neural Voice Registry)
1. `ar-SA-HamedNeural`: الصوت الأساسي للإعلانات المؤسسية، الرصانة، والشراكات التقنية B2B.
2. `ar-SA-ZariyahNeural`: الصوت الأنثوي الأساسي لتطبيقات المستهلكين، الرعاية، والتعليم التقني.
3. `ar-EG-ShakirNeural`: الصوت الحركي السريع للحملات الترويجية والريلز الفيروسية.
4. `en-US-AndrewMultilingualNeural`: الصوت الإنجليزي متعدد اللغات لنصوص B2B العالمية.
