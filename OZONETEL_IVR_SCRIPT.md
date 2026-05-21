# Divine Hindu — IVR Script for Ozonetel CloudAgent

**Brand name (spoken in every greeting):** Divine Hindu
**Caller persona (spoken name):** Kavya
**Voice provider requested:** Ozonetel Pro — Google Cloud TTS (Wavenet voices) via `<playtext type="ggl">`. **Not** pre-recorded WAVs, not standard robotic voices.
**Caller ID:** Divine Hindu's DID number (the number Ozonetel has provisioned for our account).
**Working hours:** 09:00 – 18:00 IST. Outside hours, agent-transfer option creates a callback ticket instead of dialing.

This file is the **single source of truth** for what we want played on every call. Read sections 1 → 8 in order. The exact text in every supported language is in section 7.

---

## 1. Languages we support (9)

| # | Code | Language | Google Wavenet voice (preferred) |
|---|------|----------|----------------------------------|
| 1 | en | English (Indian) | `en-IN-Wavenet-D` |
| 2 | hi | Hindi | `hi-IN-Wavenet-D` |
| 3 | ta | Tamil | `ta-IN-Wavenet-D` |
| 4 | te | Telugu | `te-IN-Standard-A` (no Wavenet available yet — use best Standard) |
| 5 | kn | Kannada | `kn-IN-Wavenet-D` |
| 6 | ml | Malayalam | `ml-IN-Wavenet-D` |
| 7 | bn | Bengali | `bn-IN-Wavenet-D` |
| 8 | mr | Marathi | `mr-IN-Wavenet-D` |
| 9 | gu | Gujarati | `gu-IN-Wavenet-D` |

All voices are female to match the persona "Kavya". If male is preferred, swap the `-D` suffix to `-B` or `-C` (same locale, different speaker).

---

## 2. The two call flows

### A. CONFIRMATION (event: ORDER_PLACED)
Fired when a customer places a new order. Asks them to confirm or request help.

```
1. English context greeting (Kavya intro)
2. Language picker (DTMF — 2 or 3 options based on state, see §3)
3. Welcome message in chosen language
4. Prompt: "Press 1 to confirm. Press 2 for help."
5a. Digit 1 → "Order confirmed" message → hang up
5b. Digit 2 (in working hours) → "Connecting to agent" → dial agent
5b. Digit 2 (after hours) → "Executive will call back in 24h" → hang up (ticket created)
5c. No input / invalid → fallback message → hang up
```

### B. REJECTION (event: ORDER_REJECTED / RTO)
Fired when a delivery attempt failed. Asks the customer to re-schedule, cancel, or talk to support.

```
1. English context greeting (Kavya intro — same as flow A)
2. Language picker
3. Welcome: "Your delivery attempt was unsuccessful today."
4. Prompt: "Press 1 to reschedule. Press 2 to cancel. Press 3 for support."
5a. Digit 1 → "Delivery rescheduled, courier will retry in 24–48h" → hang up
5b. Digit 2 → "Cancellation submitted" → hang up
5c. Digit 3 (in hours) → "Connecting to agent" → dial agent
5c. Digit 3 (after hours) → "Executive will call back in 24h" → hang up
5d. No input / invalid → fallback message → hang up
```

---

## 3. Region logic — how many languages the customer hears

We **never** play all 9 languages — that's a 30-second wait and the customer hangs up. The picker is filtered by the customer's delivery state. Always **English + Hindi** are offered; a third native language is added only when the state has one.

### 3a. State → menu mapping (ISO 3166-2:IN codes)

**3-option menu — English + Hindi + native language:**

| State code | State / UT | Menu languages | Digits assigned |
|---|---|---|---|
| TN | Tamil Nadu | en, hi, ta | 1, 2, 3 |
| PY | Puducherry | en, hi, ta | 1, 2, 3 |
| AP | Andhra Pradesh | en, hi, te | 1, 2, 3 |
| TS / TG | Telangana | en, hi, te | 1, 2, 3 |
| KA | Karnataka | en, hi, kn | 1, 2, 3 |
| KL | Kerala | en, hi, ml | 1, 2, 3 |
| LD | Lakshadweep | en, hi, ml | 1, 2, 3 |
| WB | West Bengal | en, hi, bn | 1, 2, 3 |
| TR | Tripura | en, hi, bn | 1, 2, 3 |
| AN | Andaman & Nicobar | en, hi, bn | 1, 2, 3 |
| MH | Maharashtra | en, hi, mr | 1, 2, 3 |
| GA | Goa | en, hi, mr | 1, 2, 3 |
| DN / DD | Dadra & Nagar Haveli, Daman & Diu | en, hi, mr | 1, 2, 3 |
| GJ | Gujarat | en, hi, gu | 1, 2, 3 |

**2-option menu — English + Hindi only:**
UP, BR, MP, RJ, HR, DL, PB, HP, UK/UT, CT/CG, JH, JK, LA, CH, OD/OR, AS, SK, AR, MN, MZ, NL, ML.
(Includes the entire Hindi belt, plus the North-East and Odisha where we don't have native voices in those scripts yet.)

**Default (no state available, or international caller):** English + Hindi only.

### 3b. Telecom-circle → state fallback

When the order payload doesn't carry `state`, we fall back to Ozonetel's telecom-circle indicator on the inbound webhook. Mapping:

| Circle (case-insensitive) | Resolves to state |
|---|---|
| ANDHRA PRADESH | AP |
| TELANGANA | TS |
| ASSAM | AS |
| BIHAR / BIHAR & JHARKHAND | BR |
| JHARKHAND | JH |
| CHENNAI | TN |
| TAMIL NADU / TAMIL NADU & PONDICHERRY | TN |
| DELHI / DELHI & NCR | DL |
| GUJARAT | GJ |
| HARYANA | HR |
| HIMACHAL PRADESH | HP |
| JAMMU & KASHMIR | JK |
| KARNATAKA | KA |
| KERALA | KL |
| KOLKATA / WEST BENGAL / WEST BENGAL & ANDAMAN | WB |
| MADHYA PRADESH / MADHYA PRADESH & CHHATTISGARH | MP |
| CHHATTISGARH | CT |
| MAHARASHTRA / MAHARASHTRA & GOA / MUMBAI | MH |
| GOA | GA |
| ORISSA / ODISHA | OD |
| PUNJAB | PB |
| RAJASTHAN | RJ |
| UTTAR PRADESH (any: E / W / EAST / WEST) | UP |
| UTTARAKHAND | UK |
| NORTH EAST / NORTHEAST | AS |

Suffixes `(E)`, `(W)`, `(EAST)`, `(WEST)` on a circle name are stripped before lookup. Unknown circle → defaults to (English, Hindi).

### 3c. Returning callers

The customer's chosen language is saved on the user record after their first call. On subsequent calls, **skip the picker entirely** and play the IVR directly in their saved language.

---

## 4. The opening greeting (always in English, before the picker)

This is the very first line every customer hears, before any language menu. Same voice as the rest of the call — **English Wavenet `en-IN-Wavenet-D`**.

### CONFIRMATION flow

> Namaste, I am Kavya, calling you from Divine Hindu. This call is regarding your recent order. Please choose your preferred language to continue.

### REJECTION flow

> Namaste, I am Kavya, calling you from Divine Hindu. This call is regarding your recent order delivery. Please choose your preferred language to continue.

The brand name **"Divine Hindu"** must be pronounced as written (English). Do not translate or transliterate it into any Indian script.

---

## 5. The language picker (DTMF, played after the greeting)

Each line is spoken in **its own language** using its own Wavenet voice. Order is fixed: English first, Hindi second, native third (if applicable). Digits start at 1 and are assigned in display order. Collect a single DTMF digit with a 5-second timeout.

### Examples

**Customer in Tamil Nadu (3-option menu: en, hi, ta):**
- (en, Wavenet-D) → "For English, press 1."
- (hi, Wavenet-D) → "हिंदी के लिए 2 दबाएं।"
- (ta, Wavenet-D) → "தமிழுக்கு 3 ஐ அழுத்தவும்."

**Customer in Uttar Pradesh (2-option menu: en, hi):**
- (en, Wavenet-D) → "For English, press 1."
- (hi, Wavenet-D) → "हिंदी के लिए 2 दबाएं।"

**Customer in Gujarat (3-option menu: en, hi, gu):**
- (en) → "For English, press 1."
- (hi) → "हिंदी के लिए 2 दबाएं।"
- (gu) → "ગુજરાતી માટે 3 દબાવો."

### Full menu line text per language (the **{digit}** is whatever position the language ends up at)

| Language | Menu line |
|---|---|
| en | For English, press {digit}. |
| hi | हिंदी के लिए {digit} दबाएं। |
| ta | தமிழுக்கு {digit} ஐ அழுத்தவும். |
| te | తెలుగు కోసం {digit} నొక్కండి. |
| kn | ಕನ್ನಡಕ್ಕಾಗಿ {digit} ಒತ್ತಿರಿ. |
| ml | മലയാളത്തിന് {digit} അമർത്തുക. |
| bn | বাংলার জন্য {digit} চাপুন। |
| mr | मराठीसाठी {digit} दाबा. |
| gu | ગુજરાતી માટે {digit} દબાવો. |

---

## 6. DTMF rules

- Collect length: 1 digit
- Timeout: 5 seconds
- Maximum re-prompt attempts: 1 (if no input on the picker, play the picker once more in English+Hindi only, then end with the "no input" message)
- Customer can press at any time during the prompt — do **not** wait for the prompt to finish before accepting input

Acceptable inputs:
- Language picker: 1, 2, or 3 (whichever digits are active for the customer's region)
- Confirmation IVR: 1 or 2
- Rejection IVR: 1, 2, or 3
- Any other digit / silence → fallback message → end call

---

## 7. The actual lines to speak — all prompts in all 9 languages

This is the complete prompt table. Every key (e.g. `confirm_welcome`) has exactly one translation per language. Always use the language the customer picked.

### 7.1 CONFIRMATION — welcome message (played right after the picker)

| Lang | Text |
|---|---|
| en | This call is regarding your recent order from Divine Hindu. Please confirm if you would like to place this order. |
| hi | यह कॉल Divine Hindu से आपके हाल के ऑर्डर के बारे में है। कृपया पुष्टि करें कि आप यह ऑर्डर देना चाहते हैं। |
| ta | இந்த அழைப்பு Divine Hindu இலிருந்து உங்கள் சமீபத்திய ஆர்டர் குறித்தது. இந்த ஆர்டரை வைக்க விரும்பினால் தயவுசெய்து உறுதிப்படுத்தவும். |
| te | ఈ కాల్ Divine Hindu నుండి మీ ఇటీవలి ఆర్డర్ గురించి. ఈ ఆర్డర్ ఇవ్వాలనుకుంటే దయచేసి ధృవీకరించండి. |
| kn | ಈ ಕರೆ Divine Hindu ನಿಂದ ನಿಮ್ಮ ಇತ್ತೀಚಿನ ಆರ್ಡರ್ ಕುರಿತಾಗಿದೆ. ಈ ಆರ್ಡರ್ ನೀಡಲು ದಯವಿಟ್ಟು ದೃಢೀಕರಿಸಿ. |
| ml | ഈ കോൾ Divine Hindu ൽ നിന്നുള്ള നിങ്ങളുടെ സമീപകാല ഓർഡറിനെ കുറിച്ചാണ്. ഓർഡർ നൽകാൻ ദയവായി സ്ഥിരീകരിക്കുക. |
| bn | এই কলটি Divine Hindu থেকে আপনার সাম্প্রতিক অর্ডার সম্পর্কে। অনুগ্রহ করে নিশ্চিত করুন যে আপনি এই অর্ডার দিতে চান। |
| mr | हा कॉल Divine Hindu कडून आपल्या अलीकडच्या ऑर्डरबद्दल आहे. कृपया पुष्टी करा की आपण हा ऑर्डर देऊ इच्छिता. |
| gu | આ કોલ Divine Hindu થી તમારા તાજેતરના ઓર્ડર વિશે છે. કૃપા કરીને પુષ્ટિ કરો કે તમે આ ઓર્ડર આપવા માગો છો. |

### 7.2 CONFIRMATION — prompt (DTMF 1 or 2)

| Lang | Text |
|---|---|
| en | Press 1 to confirm your order. Press 2 for help. |
| hi | ऑर्डर की पुष्टि के लिए 1 दबाएं। सहायता के लिए 2 दबाएं। |
| ta | ஆர்டரை உறுதிப்படுத்த 1 அழுத்தவும். உதவிக்கு 2 அழுத்தவும். |
| te | ఆర్డర్ ధృవీకరించడానికి 1 నొక్కండి. సహాయం కోసం 2 నొక్కండి. |
| kn | ಆರ್ಡರ್ ದೃಢೀಕರಿಸಲು 1 ಒತ್ತಿರಿ. ಸಹಾಯಕ್ಕಾಗಿ 2 ಒತ್ತಿರಿ. |
| ml | ഓർഡർ സ്ഥിരീകരിക്കാൻ 1 അമർത്തുക. സഹായത്തിന് 2 അമർത്തുക. |
| bn | অর্ডার নিশ্চিত করতে 1 চাপুন। সহায়তার জন্য 2 চাপুন। |
| mr | ऑर्डर निश्चित करण्यासाठी 1 दाबा. मदतीसाठी 2 दाबा. |
| gu | ઓર્ડરની પુષ્ટિ કરવા માટે 1 દબાવો. મદદ માટે 2 દબાવો. |

### 7.3 CONFIRMATION — digit 1 response (order confirmed → end call)

| Lang | Text |
|---|---|
| en | Your order has been confirmed successfully. Thank you for connecting with us, have a great day. |
| hi | आपका ऑर्डर सफलतापूर्वक पुष्टि कर दिया गया है। हमसे जुड़ने के लिए धन्यवाद, आपका दिन शुभ हो। |
| ta | உங்கள் ஆர்டர் வெற்றிகரமாக உறுதிசெய்யப்பட்டது. எங்களுடன் இணைந்ததற்கு நன்றி, உங்கள் நாள் இனிமையாக இருக்கட்டும். |
| te | మీ ఆర్డర్ విజయవంతంగా ధృవీకరించబడింది. మాతో కనెక్ట్ అయినందుకు ధన్యవాదాలు, మీకు మంచి రోజు కావాలని కోరుకుంటున్నాము. |
| kn | ನಿಮ್ಮ ಆರ್ಡರ್ ಯಶಸ್ವಿಯಾಗಿ ದೃಢೀಕರಿಸಲಾಗಿದೆ. ನಮ್ಮೊಂದಿಗೆ ಸಂಪರ್ಕಿಸಿದ್ದಕ್ಕಾಗಿ ಧನ್ಯವಾದಗಳು, ನಿಮಗೆ ಒಳ್ಳೆಯ ದಿನವಾಗಲಿ. |
| ml | നിങ്ങളുടെ ഓർഡർ വിജയകരമായി സ്ഥിരീകരിച്ചു. ഞങ്ങളുമായി ബന്ധപ്പെട്ടതിന് നന്ദി, നല്ല ദിവസം ആശംസിക്കുന്നു. |
| bn | আপনার অর্ডার সফলভাবে নিশ্চিত করা হয়েছে। আমাদের সাথে সংযোগ করার জন্য ধন্যবাদ, আপনার দিন শুভ হোক। |
| mr | आपला ऑर्डर यशस्वीरित्या निश्चित झाला आहे. आमच्याशी जोडल्याबद्दल धन्यवाद, आपला दिवस शुभ असो. |
| gu | તમારો ઓર્ડર સફળતાપૂર્વક પુષ્ટ થયો છે. અમારી સાથે જોડાવા બદલ આભાર, તમારો દિવસ શુભ રહે. |

### 7.4 CONFIRMATION / REJECTION — fallback (no input, invalid input → end call)

| Lang | Text |
|---|---|
| en | Sorry, I didn't catch that. Goodbye. |
| hi | क्षमा करें, मुझे समझ नहीं आया। अलविदा। |
| ta | மன்னிக்கவும், எனக்கு புரியவில்லை. நன்றி. |
| te | క్షమించండి, నాకు అర్థం కాలేదు. వీడ్కోలు. |
| kn | ಕ್ಷಮಿಸಿ, ನನಗೆ ಅರ್ಥವಾಗಲಿಲ್ಲ. ವಿದಾಯ. |
| ml | ക്ഷമിക്കണം, മനസ്സിലായില്ല. വിട. |
| bn | দুঃখিত, আমি বুঝতে পারিনি। বিদায়। |
| mr | क्षमा करा, मला समजले नाही. निरोप. |
| gu | માફ કરો, મને સમજાયું નહીં. આવજો. |

### 7.5 REJECTION — welcome message

| Lang | Text |
|---|---|
| en | Your delivery attempt was unsuccessful today. |
| hi | आज आपकी डिलिवरी का प्रयास सफल नहीं हो सका। |
| ta | இன்று உங்கள் டெலிவரி முயற்சி வெற்றிபெறவில்லை. |
| te | ఈ రోజు మీ డెలివరీ ప్రయత్నం విజయవంతం కాలేదు. |
| kn | ಇಂದು ನಿಮ್ಮ ಡೆಲಿವರಿ ಪ್ರಯತ್ನ ಯಶಸ್ವಿಯಾಗಲಿಲ್ಲ. |
| ml | ഇന്ന് നിങ്ങളുടെ ഡെലിവറി ശ്രമം വിജയിച്ചില്ല. |
| bn | আজ আপনার ডেলিভারি প্রচেষ্টা সফল হয়নি। |
| mr | आज आपला डिलिव्हरीचा प्रयत्न यशस्वी होऊ शकला नाही. |
| gu | આજે તમારો ડિલિવરી પ્રયાસ સફળ રહ્યો નથી. |

### 7.6 REJECTION — prompt (DTMF 1, 2, or 3)

| Lang | Text |
|---|---|
| en | Press 1 to reschedule the delivery. Press 2 to cancel the order. Press 3 to connect with customer support. |
| hi | डिलिवरी पुनः निर्धारित करने के लिए 1 दबाएं। ऑर्डर रद्द करने के लिए 2 दबाएं। ग्राहक सहायता से जुड़ने के लिए 3 दबाएं। |
| ta | டெலிவரியை மீண்டும் திட்டமிட 1 அழுத்தவும். ஆர்டர் ரத்து செய்ய 2 அழுத்தவும். வாடிக்கையாளர் ஆதரவை இணைக்க 3 அழுத்தவும். |
| te | డెలివరీని మళ్లీ షెడ్యూల్ చేయడానికి 1 నొక్కండి. ఆర్డర్ రద్దు చేయడానికి 2 నొక్కండి. కస్టమర్ సపోర్ట్‌తో కనెక్ట్ కావడానికి 3 నొక్కండి. |
| kn | ಡೆಲಿವರಿಯನ್ನು ಮರುನಿಗದಿಪಡಿಸಲು 1 ಒತ್ತಿರಿ. ಆರ್ಡರ್ ರದ್ದುಗೊಳಿಸಲು 2 ಒತ್ತಿರಿ. ಗ್ರಾಹಕ ಬೆಂಬಲಕ್ಕೆ ಸಂಪರ್ಕಿಸಲು 3 ಒತ್ತಿರಿ. |
| ml | ഡെലിവറി പുനഃക്രമീകരിക്കാൻ 1 അമർത്തുക. ഓർഡർ റദ്ദാക്കാൻ 2 അമർത്തുക. കസ്റ്റമർ സപ്പോർട്ടുമായി ബന്ധിപ്പിക്കാൻ 3 അമർത്തുക. |
| bn | ডেলিভারি পুনঃনির্ধারণ করতে 1 চাপুন। অর্ডার বাতিল করতে 2 চাপুন। কাস্টমার সাপোর্টের সাথে সংযোগ করতে 3 চাপুন। |
| mr | डिलिव्हरी पुन्हा शेड्यूल करण्यासाठी 1 दाबा. ऑर्डर रद्द करण्यासाठी 2 दाबा. ग्राहक सहाय्याशी जोडण्यासाठी 3 दाबा. |
| gu | ડિલિવરી ફરીથી શેડ્યૂલ કરવા માટે 1 દબાવો. ઓર્ડર રદ કરવા માટે 2 દબાવો. ગ્રાહક સહાય સાથે જોડાવા માટે 3 દબાવો. |

### 7.7 REJECTION — digit 1 response (delivery rescheduled → end call)

| Lang | Text |
|---|---|
| en | Your delivery has been rescheduled successfully. Our courier partner will attempt delivery again within the next 24 to 48 hours. Thank you for connecting with us, have a great day. |
| hi | आपकी डिलिवरी सफलतापूर्वक पुनः निर्धारित कर दी गई है। हमारा कूरियर पार्टनर अगले 24 से 48 घंटों में पुनः डिलिवरी का प्रयास करेगा। हमसे जुड़ने के लिए धन्यवाद, आपका दिन शुभ हो। |
| ta | உங்கள் டெலிவரி வெற்றிகரமாக மீண்டும் திட்டமிடப்பட்டது. எங்கள் கூரியர் பார்ட்னர் அடுத்த 24 முதல் 48 மணி நேரத்தில் மீண்டும் டெலிவரி செய்வார். எங்களுடன் இணைந்ததற்கு நன்றி, உங்கள் நாள் இனிமையாக இருக்கட்டும். |
| te | మీ డెలివరీ విజయవంతంగా మళ్లీ షెడ్యూల్ చేయబడింది. మా కొరియర్ పార్టనర్ తదుపరి 24 నుండి 48 గంటల్లో మళ్లీ డెలివరీ ప్రయత్నిస్తారు. మాతో కనెక్ట్ అయినందుకు ధన్యవాదాలు, మీకు మంచి రోజు కావాలని కోరుకుంటున్నాము. |
| kn | ನಿಮ್ಮ ಡೆಲಿವರಿ ಯಶಸ್ವಿಯಾಗಿ ಮರುನಿಗದಿಯಾಗಿದೆ. ನಮ್ಮ ಕೊರಿಯರ್ ಪಾರ್ಟ್ನರ್ ಮುಂದಿನ 24 ರಿಂದ 48 ಗಂಟೆಗಳಲ್ಲಿ ಮತ್ತೆ ಡೆಲಿವರಿ ಪ್ರಯತ್ನಿಸುತ್ತಾರೆ. ನಮ್ಮೊಂದಿಗೆ ಸಂಪರ್ಕಿಸಿದ್ದಕ್ಕಾಗಿ ಧನ್ಯವಾದಗಳು, ನಿಮಗೆ ಒಳ್ಳೆಯ ದಿನವಾಗಲಿ. |
| ml | നിങ്ങളുടെ ഡെലിവറി വിജയകരമായി പുനഃക്രമീകരിച്ചു. ഞങ്ങളുടെ കൊറിയർ പാർട്ണർ അടുത്ത 24 മുതൽ 48 മണിക്കൂറിനുള്ളിൽ വീണ്ടും ഡെലിവറി ശ്രമിക്കും. ഞങ്ങളുമായി ബന്ധപ്പെട്ടതിന് നന്ദി, നല്ല ദിവസം ആശംസിക്കുന്നു. |
| bn | আপনার ডেলিভারি সফলভাবে পুনঃনির্ধারিত হয়েছে। আমাদের কুরিয়ার পার্টনার পরবর্তী 24 থেকে 48 ঘণ্টার মধ্যে পুনরায় ডেলিভারির চেষ্টা করবে। আমাদের সাথে সংযোগ করার জন্য ধন্যবাদ, আপনার দিন শুভ হোক। |
| mr | आपली डिलिव्हरी यशस्वीरित्या पुन्हा शेड्यूल केली गेली आहे. आमचा कुरिअर पार्टनर पुढील 24 ते 48 तासांत पुन्हा डिलिव्हरीचा प्रयत्न करेल. आमच्याशी जोडल्याबद्दल धन्यवाद, आपला दिवस शुभ असो. |
| gu | તમારી ડિલિવરી સફળતાપૂર્વક ફરીથી શેડ્યૂલ કરવામાં આવી છે. અમારો કુરિયર પાર્ટનર આગામી 24 થી 48 કલાકમાં ફરીથી ડિલિવરીનો પ્રયાસ કરશે. અમારી સાથે જોડાવા બદલ આભાર, તમારો દિવસ શુભ રહે. |

### 7.8 REJECTION — digit 2 response (order cancelled → end call)

| Lang | Text |
|---|---|
| en | Your cancellation request has been submitted successfully. Thank you for connecting with us, have a great day. |
| hi | आपका रद्द करने का अनुरोध सफलतापूर्वक प्राप्त हो गया है। हमसे जुड़ने के लिए धन्यवाद, आपका दिन शुभ हो। |
| ta | உங்கள் ரத்து கோரிக்கை வெற்றிகரமாக சமர்பிக்கப்பட்டது. எங்களுடன் இணைந்ததற்கு நன்றி, உங்கள் நாள் இனிமையாக இருக்கட்டும். |
| te | మీ రద్దు అభ్యర్థన విజయవంతంగా సమర్పించబడింది. మాతో కనెక్ట్ అయినందుకు ధన్యవాదాలు, మీకు మంచి రోజు కావాలని కోరుకుంటున్నాము. |
| kn | ನಿಮ್ಮ ರದ್ದತಿ ವಿನಂತಿ ಯಶಸ್ವಿಯಾಗಿ ಸಲ್ಲಿಸಲಾಗಿದೆ. ನಮ್ಮೊಂದಿಗೆ ಸಂಪರ್ಕಿಸಿದ್ದಕ್ಕಾಗಿ ಧನ್ಯವಾದಗಳು, ನಿಮಗೆ ಒಳ್ಳೆಯ ದಿನವಾಗಲಿ. |
| ml | നിങ്ങളുടെ റദ്ദാക്കൽ അഭ്യർത്ഥന വിജയകരമായി സമർപ്പിച്ചു. ഞങ്ങളുമായി ബന്ധപ്പെട്ടതിന് നന്ദി, നല്ല ദിവസം ആശംസിക്കുന്നു. |
| bn | আপনার বাতিলের অনুরোধ সফলভাবে জমা দেওয়া হয়েছে। আমাদের সাথে সংযোগ করার জন্য ধন্যবাদ, আপনার দিন শুভ হোক। |
| mr | आपली रद्द करण्याची विनंती यशस्वीरित्या सबमिट केली गेली आहे. आमच्याशी जोडल्याबद्दल धन्यवाद, आपला दिवस शुभ असो. |
| gu | તમારી રદ કરવાની વિનંતી સફળતાપૂર્વક સબમિટ કરવામાં આવી છે. અમારી સાથે જોડાવા બદલ આભાર, તમારો દિવસ શુભ રહે. |

### 7.9 "Connecting to agent" (CONFIRMATION digit 2 or REJECTION digit 3, in working hours)

Spoken right before the transfer / dial happens.

| Lang | Text |
|---|---|
| en | Please wait while we connect you to our customer support executive. |
| hi | कृपया प्रतीक्षा करें, हम आपको हमारे ग्राहक सहायता प्रतिनिधि से जोड़ रहे हैं। |
| ta | தயவுசெய்து காத்திருக்கவும், எங்கள் வாடிக்கையாளர் ஆதரவு பிரதிநிதியுடன் உங்களை இணைக்கிறோம். |
| te | దయచేసి వేచి ఉండండి, మేము మిమ్మల్ని మా కస్టమర్ సపోర్ట్ ఎగ్జిక్యూటివ్‌కు కనెక్ట్ చేస్తున్నాము. |
| kn | ದಯವಿಟ್ಟು ಕಾಯಿರಿ, ನಾವು ನಿಮ್ಮನ್ನು ನಮ್ಮ ಗ್ರಾಹಕ ಬೆಂಬಲ ಪ್ರತಿನಿಧಿಗೆ ಸಂಪರ್ಕಿಸುತ್ತಿದ್ದೇವೆ. |
| ml | ദയവായി കാത്തിരിക്കുക, ഞങ്ങൾ നിങ്ങളെ ഞങ്ങളുടെ കസ്റ്റമർ സപ്പോർട്ട് എക്സിക്യൂട്ടീവുമായി ബന്ധിപ്പിക്കുന്നു. |
| bn | অনুগ্রহ করে অপেক্ষা করুন, আমরা আপনাকে আমাদের কাস্টমার সাপোর্ট এক্সিকিউটিভের সাথে সংযুক্ত করছি। |
| mr | कृपया थांबा, आम्ही आपल्याला आमच्या ग्राहक सहाय्य प्रतिनिधीशी जोडत आहोत. |
| gu | કૃપા કરીને રાહ જુઓ, અમે તમને અમારા ગ્રાહક સહાય પ્રતિનિધિ સાથે જોડી રહ્યા છીએ. |

### 7.10 After-hours callback (CONFIRMATION digit 2 or REJECTION digit 3, outside 09:00–18:00 IST)

| Lang | Text |
|---|---|
| en | Our executive will connect with you within the next 24 hours. Thank you for connecting with us. |
| hi | हमारा प्रतिनिधि अगले 24 घंटों में आपसे संपर्क करेगा। हमसे जुड़ने के लिए धन्यवाद। |
| ta | எங்கள் பிரதிநிதி அடுத்த 24 மணி நேரத்தில் உங்களுடன் தொடர்பு கொள்வார். எங்களுடன் இணைந்ததற்கு நன்றி. |
| te | మా ఎగ్జిక్యూటివ్ తదుపరి 24 గంటల్లో మీతో కనెక్ట్ అవుతారు. మాతో కనెక్ట్ అయినందుకు ధన్యవాదాలు. |
| kn | ನಮ್ಮ ಪ್ರತಿನಿಧಿ ಮುಂದಿನ 24 ಗಂಟೆಗಳಲ್ಲಿ ನಿಮ್ಮನ್ನು ಸಂಪರ್ಕಿಸುತ್ತಾರೆ. ನಮ್ಮೊಂದಿಗೆ ಸಂಪರ್ಕಿಸಿದ್ದಕ್ಕಾಗಿ ಧನ್ಯವಾದಗಳು. |
| ml | ഞങ്ങളുടെ എക്സിക്യൂട്ടീവ് അടുത്ത 24 മണിക്കൂറിനുള്ളിൽ നിങ്ങളെ ബന്ധപ്പെടും. ഞങ്ങളുമായി ബന്ധപ്പെട്ടതിന് നന്ദി. |
| bn | আমাদের এক্সিকিউটিভ পরবর্তী 24 ঘণ্টার মধ্যে আপনার সাথে সংযোগ করবে। আমাদের সাথে সংযোগ করার জন্য ধন্যবাদ। |
| mr | आमचा प्रतिनिधी पुढील 24 तासांत आपल्याशी संपर्क साधेल. आमच्याशी जोडल्याबद्दल धन्यवाद. |
| gu | અમારો પ્રતિનિધિ આગામી 24 કલાકમાં તમારી સાથે સંપર્ક કરશે. અમારી સાથે જોડાવા બદલ આભાર. |

### 7.11 "No response received — we will call you back" (max retries reached on the picker, end call)

| Lang | Text |
|---|---|
| en | Sorry, we did not receive a valid response. We will call you back. Goodbye. |
| hi | हमें कोई जवाब नहीं मिला। हम वापस कॉल करेंगे। |
| ta | எந்த பதிலும் கிடைக்கவில்லை. மீண்டும் அழைக்கிறோம். |
| te | మాకు సమాధానం రాలేదు. మేము తిరిగి కాల్ చేస్తాము. |
| kn | ನಮಗೆ ಪ್ರತಿಕ್ರಿಯೆ ಸಿಗಲಿಲ್ಲ. ನಾವು ಮರಳಿ ಕರೆ ಮಾಡುತ್ತೇವೆ. |
| ml | ഞങ്ങൾക്ക് മറുപടി ലഭിച്ചില്ല. ഞങ്ങൾ വീണ്ടും വിളിക്കും. |
| bn | আমরা কোনো উত্তর পাইনি। আমরা আপনাকে আবার কল করব। |
| mr | प्रतिसाद मिळाला नाही. आम्ही परत कॉल करू. |
| gu | કોઈ જવાબ મળ્યો નથી. અમે પાછા કોલ કરીશું. |

### 7.12 "Invalid input" (customer pressed a digit not in the menu)

| Lang | Text |
|---|---|
| en | Invalid input. Goodbye. |
| hi | अमान्य इनपुट। अलविदा। |
| ta | தவறான உள்ளீடு. நன்றி. |
| te | చెల్లని ఇన్‌పుట్. వీడ్కోలు. |
| kn | ಅಮಾನ್ಯ ಇನ್ಪುಟ್. ವಿದಾಯ. |
| ml | അസാധുവായ ഇൻപുട്ട്. വിട. |
| bn | অবৈধ ইনপুট। বিদায়। |
| mr | अवैध इनपुट. निरोप. |
| gu | અમાન્ય ઇનપુટ. આવજો. |

---

## 8. End-to-end example — CONFIRMATION call to a customer in Tamil Nadu

```
[CALLER PICKS UP]

(en, Wavenet-D)
"Namaste, I am Kavya, calling you from Divine Hindu. This call is regarding
 your recent order. Please choose your preferred language to continue."

(en, Wavenet-D) → "For English, press 1."
(hi, Wavenet-D) → "हिंदी के लिए 2 दबाएं।"
(ta, Wavenet-D) → "தமிழுக்கு 3 ஐ அழுத்தவும்."

[COLLECT 1 DTMF DIGIT, TIMEOUT 5s]

  Customer presses 3 → set language = Tamil.

(ta, Wavenet-D)
"இந்த அழைப்பு Divine Hindu இலிருந்து உங்கள் சமீபத்திய ஆர்டர் குறித்தது.
 இந்த ஆர்டரை வைக்க விரும்பினால் தயவுசெய்து உறுதிப்படுத்தவும்."

(ta, Wavenet-D)
"ஆர்டரை உறுதிப்படுத்த 1 அழுத்தவும். உதவிக்கு 2 அழுத்தவும்."

[COLLECT 1 DTMF DIGIT, TIMEOUT 5s]

  Customer presses 1.

(ta, Wavenet-D)
"உங்கள் ஆர்டர் வெற்றிகரமாக உறுதிசெய்யப்பட்டது. எங்களுடன் இணைந்ததற்கு நன்றி,
 உங்கள் நாள் இனிமையாக இருக்கட்டும்."

[HANG UP]
```

---

## 9. Implementation notes for Ozonetel

1. **Use `<playtext type="ggl" lang="<bcp47>" voice="<wavenet>">…</playtext>`** for all 9 languages. Even English and Hindi go through Google TTS (not KooKoo's native voice), so the voice is consistent across the whole call.
2. **Brand name "Divine Hindu" is always English-script text inside every prompt**, even Tamil/Telugu/etc. Google TTS will read it correctly. Do not transliterate.
3. **Picker languages are filtered before the IVR starts** — the wrapper code passes the customer's state (or telecom circle) to the Campaign and only the appropriate 2 or 3 menu lines are played.
4. **Digit collection:** `<collectdtmf l="1" o="5000">`. No speech recognition during the picker — DTMF only (the customer hasn't picked a language yet, so we can't reliably understand speech).
5. **After-hours behaviour:** if the customer presses the "help" digit between 18:00–09:00 IST, **do not transfer** — play §7.10 and end the call. Our backend creates a callback ticket in Chatwoot. Working hours are configurable per campaign.
6. **Returning callers:** if our backend already knows the customer's language (from a previous call), the wrapper API call passes `lang=<code>` and the picker is skipped. The IVR jumps straight to §7.1 (CONFIRMATION) or §7.5 (REJECTION) in that language.
7. **Retry on no input:** the picker is re-played once. If the customer is silent the second time, play §7.11 in English+Hindi and end the call. The retry engine will schedule another attempt.

---

## 10. What we need from Ozonetel customer care to go live

1. Enable Google Cloud TTS (`<playtext type="ggl">`) on our CloudAgent Pro account — all 9 BCP-47 locales above.
2. Create a Campaign that hits our webhook (we'll provide the URL: `https://<our-public-domain>/webhook/voice-start`) and passes the standard params (`cid`, `sid`, `event`, `circle`).
3. Provision the agent transfer destination (the SIP / mobile number that should ring when a customer presses the "help" digit in working hours).
4. Confirm the DID (caller ID) we can use for outbound calls.
5. Confirm we can trigger calls via the AddCampaignData API (`POST https://api.cloudagent.ozonetel.com/ca_apis/AddCampaignData` with the `apiKey` header).

Please get back to us with: Campaign ID, DID, API key, and confirmation that Wavenet voices are enabled for our account.
