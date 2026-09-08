/**
 * Nepali/English UI text.
 *
 * The consent document itself is NOT covered here -- it's a fixed legal text
 * served bilingually by the server (docs/consent-ne.md) and rendered as-is
 * regardless of this toggle. This module only covers the surrounding chrome:
 * labels, buttons, status and error messages.
 *
 * Default is English; a contributor's choice persists in localStorage.
 */

const STORAGE_KEY = 'voiceai.lang';
const DEFAULT_LANG = 'en';

export const STRINGS = {
  'meta.title': { en: 'Voice Recording — voice.cloudfrm.ai', ne: 'आवाज रेकर्डिङ — voice.cloudfrm.ai' },
  'brand.tag': { en: 'Nepali voice collection', ne: 'नेपाली आवाज संकलन' },

  // --- consent step -------------------------------------------------------
  'consent.heading': { en: 'Your voice, for the Nepali language', ne: 'तपाईंको आवाज, नेपाली भाषाका लागि' },
  'consent.lede': {
    en: 'This project collects voices in Nepali and other mother tongues, so computers can understand and speak our language. You will read a few sentences — about 15–20 minutes.',
    ne: 'यो परियोजनाले नेपाली र अन्य मातृभाषाहरूको आवाज संकलन गर्छ, ताकि कम्प्युटरले हाम्रो भाषा बुझ्न र बोल्न सिकोस्। तपाईंले केही वाक्य पढ्नुहुनेछ — करिब १५–२० मिनेट।',
  },
  'consent.specQuality': { en: 'Quality', ne: 'गुणस्तर' },
  'consent.specSnr': { en: 'SNR needed', ne: 'चाहिने SNR' },
  'consent.specTime': { en: 'Time', ne: 'समय' },
  'consent.specTimeValue': { en: '15–20 minutes', ne: '१५–२० मिनेट' },
  'consent.heading2': { en: 'Consent', ne: 'सहमति' },
  'consent.loading': { en: 'Loading…', ne: 'लोड हुँदैछ…' },
  'consent.versionLabel': { en: 'Consent version:', ne: 'सहमति संस्करण:' },
  'consent.agree': {
    en: 'I have read and understood the consent above. I agree to participate voluntarily.',
    ne: 'मैले माथिको सहमति पढेँ र बुझेँ। म स्वेच्छाले सहभागी हुन सहमत छु।',
  },
  'consent.continue': { en: 'Continue', ne: 'अगाडि बढ्नुहोस्' },

  // --- choose recording method step ------------------------------------------
  'method.eyebrow': { en: 'Next step', ne: 'अर्को चरण' },
  'method.headingPre': { en: 'Choose Your', ne: 'आफ्नो' },
  'method.headingAccent': { en: 'Recording Method', ne: 'रेकर्डिङ विधि छान्नुहोस्' },
  'method.lede': { en: "Select how you'd like to contribute your voice.", ne: 'तपाईं कसरी आफ्नो आवाज योगदान गर्न चाहनुहुन्छ छान्नुहोस्।' },
  'method.guidedTitle': { en: 'Guided Recording', ne: 'निर्देशित रेकर्डिङ' },
  'method.guidedSub': { en: 'Record with guidance', ne: 'निर्देशनसहित रेकर्ड गर्नुहोस्' },
  'method.guidedDesc': {
    en: "You'll be provided with a set of sentences to read aloud, one at a time.",
    ne: 'तपाईंलाई एक–एक गरी पढ्नका लागि वाक्यहरू दिइनेछ।',
  },
  'method.guidedCta': { en: 'Start guided recording', ne: 'निर्देशित रेकर्डिङ सुरु गर्नुहोस्' },
  'method.freeTitle': { en: 'Free Recording', ne: 'स्वतन्त्र रेकर्डिङ' },
  'method.freeSub': { en: 'Record your own voice', ne: 'आफ्नै आवाज रेकर्ड गर्नुहोस्' },
  'method.freeDesc': {
    en: 'Submit up to 8 hours of your own voice recordings. Upload the corresponding transcript and script with your recordings.',
    ne: 'आफ्नो ८ घण्टासम्मको आवाज रेकर्डिङ पेश गर्नुहोस्। रेकर्डिङसँगै सम्बन्धित ट्रान्सक्रिप्ट र स्क्रिप्ट अपलोड गर्नुहोस्।',
  },
  'method.freeCta': { en: 'Upload recording', ne: 'रेकर्डिङ अपलोड गर्नुहोस्' },
  'method.footnote': { en: 'You can choose either recording method.', ne: 'तपाईं कुनै पनि रेकर्डिङ विधि छान्न सक्नुहुन्छ।' },

  // --- save-profile step (shown AFTER recording) -----------------------------
  'save.heading': { en: 'Almost done — tell us about yourself', ne: 'करिब सकियो — आफ्नो बारेमा बताउनुहोस्' },
  'save.lede': {
    en: 'You’ve finished recording. These optional details help measure linguistic diversity in the dataset. Your name, email and phone are never linked to the recording, and never go into the dataset.',
    ne: 'तपाईंको रेकर्डिङ सकियो। यी वैकल्पिक विवरणले डेटासेटमा भाषिक विविधता मापन गर्न मद्दत गर्छ। तपाईंको नाम, इमेल र फोन कहिल्यै रेकर्डिङसँग जोडिँदैन, र डेटासेटमा जाँदैन।',
  },
  'save.submit': { en: 'Save and finish', ne: 'सुरक्षित गरी पूरा गर्नुहोस्' },
  'profile.contact': { en: 'Contact', ne: 'सम्पर्क' },
  'profile.optional': { en: '(optional)', ne: '(वैकल्पिक)' },
  'profile.name': { en: 'Name', ne: 'नाम' },
  'profile.email': { en: 'Email', ne: 'इमेल' },
  'profile.phone': { en: 'Phone', ne: 'फोन' },
  'profile.languageGroup': { en: 'Language', ne: 'भाषा' },
  'profile.motherTongue': { en: 'Mother tongue', ne: 'मातृभाषा' },
  'profile.choose': { en: 'Choose one', ne: 'छान्नुहोस्' },
  'profile.dialect': { en: 'Dialect / accent', ne: 'भाषिका / लवज' },
  'profile.dialectPlaceholder': { en: 'e.g.: Eastern, Doteli', ne: 'जस्तै: पूर्वी, डोट्याली' },
  'profile.region': { en: 'Region', ne: 'क्षेत्र' },
  'profile.regionNote': {
    en: 'Full address is not asked. Province–district–municipality is enough to distinguish dialect.',
    ne: 'पूरा ठेगाना सोधिँदैन। प्रदेश–जिल्ला–पालिकाले भाषिका छुट्याउन पुग्छ।',
  },
  'profile.province': { en: 'Province', ne: 'प्रदेश' },
  'profile.district': { en: 'District', ne: 'जिल्ला' },
  'profile.municipality': { en: 'Municipality', ne: 'नगरपालिका / गाउँपालिका' },
  'profile.ward': { en: 'Ward', ne: 'वडा' },
  'profile.otherGroup': { en: 'Other', ne: 'अन्य' },
  'profile.ageBand': { en: 'Age group', ne: 'उमेर समूह' },
  'profile.gender': { en: 'Gender', ne: 'लिङ्ग' },
  'profile.genderFemale': { en: 'Female', ne: 'महिला' },
  'profile.genderMale': { en: 'Male', ne: 'पुरुष' },
  'profile.genderOther': { en: 'Other', ne: 'अन्य' },
  'profile.preferNotToSay': { en: 'Prefer not to say', ne: 'भन्न चाहन्न' },
  'profile.education': { en: 'Education', ne: 'शिक्षा' },
  'profile.eduPrimary': { en: 'Primary', ne: 'प्राथमिक' },
  'profile.eduSecondary': { en: 'Secondary', ne: 'माध्यमिक' },
  'profile.eduBachelor': { en: "Bachelor's", ne: 'स्नातक' },
  'profile.eduMasterPlus': { en: "Master's or above", ne: 'स्नातकोत्तर वा माथि' },
  'profile.casteLabel': { en: 'Caste / ethnicity', ne: 'जात / जातीयता' },
  'profile.casteOptional': { en: '(optional — fine to skip)', ne: '(वैकल्पिक — नभने पनि हुन्छ)' },
  'profile.castePlaceholder': { en: 'Leave blank if you prefer not to say', ne: 'भन्न चाहनुहुन्न भने खाली छोड्नुहोस्' },
  'profile.casteNote': {
    en: 'This is sensitive personal information (Individual Privacy Act 2075, section 27(2)). It is never linked to the recording and never enters the dataset.',
    ne: 'यो संवेदनशील व्यक्तिगत सूचना हो (व्यक्तिगत गोपनीयता ऐन २०७५, दफा २७(२))। यो रेकर्डिङसँग जोडिँदैन र डेटासेटमा कहिल्यै जाँदैन।',
  },

  // --- mother tongue / province / options ------------------------------------
  'mt.nepali': { en: 'Nepali', ne: 'नेपाली' },
  'mt.maithili': { en: 'Maithili', ne: 'मैथिली' },
  'mt.bhojpuri': { en: 'Bhojpuri', ne: 'भोजपुरी' },
  'mt.tharu': { en: 'Tharu', ne: 'थारू' },
  'mt.tamang': { en: 'Tamang', ne: 'तामाङ' },
  'mt.newar': { en: 'Newar', ne: 'नेवार' },
  'mt.magar': { en: 'Magar', ne: 'मगर' },
  'mt.bajjika': { en: 'Bajjika', ne: 'बज्जिका' },
  'mt.doteli': { en: 'Doteli', ne: 'डोटेली' },
  'mt.awadhi': { en: 'Awadhi', ne: 'अवधी' },
  'mt.limbu': { en: 'Limbu', ne: 'लिम्बू' },
  'mt.other': { en: 'Other', ne: 'अन्य' },
  'province.koshi': { en: 'Koshi', ne: 'कोशी' },
  'province.madhesh': { en: 'Madhesh', ne: 'मधेश' },
  'province.bagmati': { en: 'Bagmati', ne: 'बागमती' },
  'province.gandaki': { en: 'Gandaki', ne: 'गण्डकी' },
  'province.lumbini': { en: 'Lumbini', ne: 'लुम्बिनी' },
  'province.karnali': { en: 'Karnali', ne: 'कर्णाली' },
  'province.sudurpashchim': { en: 'Sudurpashchim', ne: 'सुदूरपश्चिम' },

  // --- mic check step -------------------------------------------------------
  'mic.heading': { en: 'Microphone check', ne: 'माइक जाँच' },
  'mic.lede': { en: "Let's make sure everything sounds right.", ne: 'सबै कुरा ठीक सुनिन्छ भनी पक्का गरौं।' },
  'mic.idLabel': { en: 'Your ID number:', ne: 'तपाईंको पहिचान नम्बर:' },
  'mic.copyId': { en: 'Copy ID', ne: 'ID प्रतिलिपि गर्नुहोस्' },
  'mic.rule1': {
    en: 'Choose a small, soft room — a room with a bed and curtains is better than a big empty hall.',
    ne: 'सानो, नरम कोठा रोज्नुहोस् — ओछ्यान र पर्दा भएको कोठा ठूलो खाली हल भन्दा राम्रो।',
  },
  'mic.rule2': {
    en: 'Close doors and windows. Turn off fans, AC, coolers and TV.',
    ne: 'झ्याल–ढोका बन्द गर्नुहोस्। पंखा, AC, कुलर र TV निभाउनुहोस्।',
  },
  'mic.rule3a': { en: 'Put your phone on', ne: 'फोन' },
  'mic.rule3strong': { en: 'silent', ne: 'साइलेन्ट' },
  'mic.rule3b': { en: '— not vibrate.', ne: 'गर्नुहोस् — भाइब्रेट होइन।' },
  'mic.rule4': {
    en: 'Keep the mic 15–20 cm from your mouth, slightly to the side.',
    ne: 'माइक मुखबाट १५–२० सेमी टाढा, अलि छेउतिर राख्नुहोस्।',
  },
  'mic.rule5a': { en: 'Use a wired headset.', ne: 'तार भएको हेडसेट प्रयोग गर्नुहोस्।' },
  'mic.rule5strong': { en: 'Do not use Bluetooth.', ne: 'ब्लुटुथ नचलाउनुहोस्।' },
  'mic.rule6': {
    en: 'Speak at a natural pace — don’t read like a news anchor.',
    ne: 'स्वाभाविक गतिमा बोल्नुहोस् — समाचार वाचक जसरी नपढ्नुहोस्।',
  },
  'mic.micLabel': { en: 'Mic', ne: 'माइक' },
  'mic.rateLabel': { en: 'Rate', ne: 'दर' },
  'mic.roomFloorLabel': { en: 'Room noise', ne: 'कोठाको आवाज' },
  'mic.begin': { en: 'Start recording', ne: 'रेकर्डिङ सुरु गर्नुहोस्' },
  'mic.unknownLabel': { en: 'Unknown microphone', ne: 'अज्ञात माइक' },
  'mic.problemLowRate': {
    en: 'This mic only runs at {rate} Hz — remove the Bluetooth headset and use a wired mic instead.',
    ne: 'यो माइक {rate} Hz मा मात्र चल्छ — ब्लुटुथ हेडसेट हटाएर तार भएको माइक प्रयोग गर्नुहोस्।',
  },
  'mic.problemBluetooth': {
    en: 'A Bluetooth mic was detected — it drops audio to 8/16 kHz. Use a wired headset instead.',
    ne: 'ब्लुटुथ माइक पत्ता लाग्यो — यसले आवाज ८/१६ kHz मा झार्छ। तार भएको हेडसेट प्रयोग गर्नुहोस्।',
  },
  'mic.problemDspNotDisabled': {
    en: 'The browser refused to turn off {label}.',
    ne: 'ब्राउजरले {label} बन्द गर्न मानेन।',
  },
  'mic.dspEchoCancellation': { en: 'echo cancellation', ne: 'इको क्यान्सिलेसन' },
  'mic.dspNoiseSuppression': { en: 'noise suppression', ne: 'नोइज सप्रेसन' },
  'mic.dspAutoGainControl': { en: 'auto gain control', ne: 'अटो गेन कन्ट्रोल' },
  'mic.seeWarnings': { en: 'See the warnings.', ne: 'चेतावनी हेर्नुहोस्।' },
  'mic.testingRoom': {
    en: 'Testing your room — stay quiet ({seconds}s)',
    ne: 'तपाईंको कोठा जाँचिँदै — चुप बस्नुहोस् ({seconds}s)',
  },
  'mic.roomGoodStarting': { en: 'Room is good ✓ — starting…', ne: 'कोठा राम्रो छ ✓ — सुरु हुँदैछ…' },

  // --- record step ------------------------------------------------------------
  'record.sentLabel': { en: 'Sent:', ne: 'पठाइएको:' },
  'record.start': { en: 'Record', ne: 'रेकर्ड गर्नुहोस्' },
  'record.stop': { en: 'Stop', ne: 'रोक्नुहोस्' },
  'record.retake': { en: 'Retake', ne: 'फेरि रेकर्ड' },
  'record.accept': { en: 'Send', ne: 'पठाउनुहोस्' },
  'record.next': { en: 'Next sentence', ne: 'अर्को वाक्य' },
  'record.footnote': {
    en: 'Wait half a second before and after speaking. Each sentence should be 4–10 seconds.',
    ne: 'बोल्नु अघि र सकेपछि आधा सेकेन्ड पर्खनुहोस्। हरेक वाक्य ४–१० सेकेन्डको हुनुपर्छ।',
  },
  'record.autoSaveNote': {
    en: 'Your progress saves automatically after every sentence you send — you can stop anytime and finish the rest later on this device.',
    ne: 'तपाईंले पठाउने हरेक वाक्यपछि प्रगति स्वतः सुरक्षित हुन्छ — तपाईं जुनसुकै बेला रोकेर यही यन्त्रमा बाँकी पछि पूरा गर्न सक्नुहुन्छ।',
  },
  'record.saveLater': { en: 'Save and continue later', ne: 'सुरक्षित गरी पछि जारी राख्नुहोस्' },
  'record.discard': { en: 'Discard session', ne: 'सत्र मेटाउनुहोस्' },
  'record.discardConfirm': {
    en: 'This deletes every sentence you’ve already sent and ends this session — you’ll go back to the start to begin a new one. This cannot be undone.',
    ne: 'यसले तपाईंले पठाइसक्नुभएका सबै वाक्य मेट्नेछ र यो सत्र अन्त्य गर्नेछ — तपाईं नयाँ सत्र सुरु गर्न फेरि सुरुमा जानुहुनेछ। यो फिर्ता गर्न सकिँदैन।',
  },
  'status.discarding': { en: 'Discarding…', ne: 'मेटाइँदै…' },

  // --- technical details box (record step) ---------------------------------
  'record.techHeading': { en: 'Technical details', ne: 'प्राविधिक विवरण' },
  'tech.sampleRate': { en: 'Sample rate', ne: 'स्याम्पल दर' },
  'tech.bitDepth': { en: 'Bit depth', ne: 'बिट गहिराइ' },
  'tech.bitDepthValue': { en: '16-bit', ne: '१६-बिट' },
  'tech.channels': { en: 'Channels', ne: 'च्यानल' },
  'tech.mono': { en: 'Mono', ne: 'मोनो' },
  'tech.format': { en: 'Format', ne: 'ढाँचा' },
  'tech.pcmWav': { en: 'WAV (PCM)', ne: 'WAV (PCM)' },
  'tech.compression': { en: 'Compression', ne: 'सङ्कुचन' },
  'tech.none': { en: 'Uncompressed', ne: 'असङ्कुचित' },
  'tech.liveLevel': { en: 'Live level', ne: 'लाइभ स्तर' },
  'tech.fileSize': { en: 'Est. size', ne: 'अनुमानित साइज' },

  // --- paused (left mid-session, resumable on this device) ----------------------
  'paused.heading': { en: 'Saved — come back anytime', ne: 'सुरक्षित भयो — जुनसुकै बेला फर्कनुहोस्' },
  'paused.summaryPre': { en: 'You’ve recorded', ne: 'तपाईंले' },
  'paused.summaryMid': { en: 'of', ne: 'मध्ये' },
  'paused.summaryPost': {
    en: 'sentences so far. Nothing is lost — come back to this page on this device to finish the rest.',
    ne: 'वाक्य रेकर्ड गर्नुभयो। केही हराउँदैन — बाँकी पूरा गर्न यही यन्त्रमा यो पृष्ठमा फर्कनुहोस्।',
  },
  'paused.continueNow': { en: 'Continue now', ne: 'अहिले जारी राख्नुहोस्' },

  'metric.duration': { en: 'Duration', ne: 'अवधि' },
  'metric.peak': { en: 'Level (peak)', ne: 'स्तर (peak)' },
  'metric.snr': { en: 'SNR', ne: 'SNR' },
  'metric.roomNoise': { en: 'Room noise', ne: 'कोठाको आवाज' },

  // --- client-side QC reasons (audio.js gate()) --------------------------------
  'qc.noSpeech': {
    en: 'No speech detected — bring the mic closer and speak again.',
    ne: 'कुनै आवाज पत्ता लागेन — माइक नजिक ल्याएर फेरि बोल्नुहोस्।',
  },
  'qc.tooShort': {
    en: 'Recording is too short ({duration}s) — read the whole sentence.',
    ne: 'रेकर्डिङ धेरै छोटो छ ({duration}s) — पूरा वाक्य पढ्नुहोस्।',
  },
  'qc.tooLong': {
    en: 'Recording is too long ({duration}s) — stop as soon as the sentence ends.',
    ne: 'रेकर्डिङ धेरै लामो छ ({duration}s) — वाक्य सकिनेबित्तिकै रोक्नुहोस्।',
  },
  'qc.clipped': {
    en: 'Audio is distorted — move the mic a bit further away or speak more softly.',
    ne: 'आवाज बिग्रिएको छ — माइक अलि टाढा सार्नुहोस् वा बिस्तारै बोल्नुहोस्।',
  },
  'qc.tooLoud': {
    en: 'Audio is too loud — keep the mic 15–20 cm from your mouth.',
    ne: 'आवाज धेरै ठूलो छ — माइक मुखबाट १५–२० सेमी टाढा राख्नुहोस्।',
  },
  'qc.tooQuiet': {
    en: 'Audio is too quiet — bring the mic closer and speak a bit louder.',
    ne: 'आवाज धेरै सानो छ — माइक नजिक ल्याउनुहोस् र अलि ठूलो स्वरमा बोल्नुहोस्।',
  },
  'qc.noisy': {
    en: 'Too much background noise — turn off fans/close windows.',
    ne: 'पछाडिको आवाज धेरै छ — पंखा/झ्याल बन्द गर्नुहोस्।',
  },
  // Distinct from 'noisy': this fires even when the room measured fine --
  // the recorded voice just wasn't loud enough above whatever floor there
  // was, so the fix is about the voice, not the room. ('noisy' fires
  // separately, with its own room-focused message, when the floor itself was
  // actually too high.)
  'qc.lowSnr': {
    en: 'Your voice was too quiet next to the background — speak a bit louder or move closer to the mic, and avoid long pauses mid-sentence.',
    ne: 'तपाईंको आवाज पछाडिको आवाजको तुलनामा धेरै सानो थियो — अलि ठूलो स्वरमा वा माइक नजिक भएर बोल्नुहोस्, र वाक्यको बीचमा लामो रोक नराख्नुहोस्।',
  },
  // Server-only checks (audio_qc/gate.py) -- the client can't measure these
  // itself before upload, so they only ever come back from a completed clip.
  'qc.sampleRateLow': {
    en: 'Recording quality is too low — don’t use a Bluetooth headset, use a wired mic instead.',
    ne: 'रेकर्डिङ गुणस्तर कम छ — ब्लुटुथ हेडसेट नचलाउनुहोस्, तार भएको माइक प्रयोग गर्नुहोस्।',
  },
  'qc.leadSilenceLong': {
    en: 'Too much silence at the start — start speaking within half a second of pressing record.',
    ne: 'सुरुमा धेरै लामो चुप्पी छ — रेकर्ड थालेको आधा सेकेन्डमै बोल्न सुरु गर्नुहोस्।',
  },
  'qc.trailSilenceLong': {
    en: 'Too much silence at the end — stop within half a second of finishing the sentence.',
    ne: 'अन्त्यमा धेरै लामो चुप्पी छ — वाक्य सकिएको आधा सेकेन्डमा रोक्नुहोस्।',
  },

  // --- blocked (storage preflight failure) screen ------------------------------
  'blocked.heading': { en: 'Cannot record right now', ne: 'अहिले रेकर्ड गर्न मिल्दैन' },
  'blocked.footnote': {
    en: 'You did nothing wrong. This check runs before recording starts, so your time isn’t wasted.',
    ne: 'तपाईंले केही गलत गर्नुभएको होइन। यो जाँच रेकर्डिङ सुरु गर्नुअघि नै गरिन्छ, ताकि तपाईंको समय खेर नजाओस्।',
  },
  'blocked.retry': { en: 'Try again', ne: 'फेरि प्रयास गर्नुहोस्' },

  // --- done screen -------------------------------------------------------------
  'done.heading': { en: 'Thank you 🙏', ne: 'धन्यवाद 🙏' },
  'done.summaryPre': { en: 'You recorded', ne: 'तपाईंले' },
  'done.summaryPost': {
    en: 'sentences. This voice will be used for the Nepali language.',
    ne: 'वाक्य रेकर्ड गर्नुभयो। यो आवाज नेपाली भाषाका लागि प्रयोग हुनेछ।',
  },
  'done.idLabel': { en: 'Your ID number:', ne: 'तपाईंको पहिचान नम्बर:' },
  'done.withdrawNote': {
    en: 'If you want your data removed, contact us with this number.',
    ne: 'डेटा हटाउन चाहनुभयो भने यही नम्बर सहित सम्पर्क गर्नुहोस्।',
  },

  // --- status / error messages --------------------------------------------------
  'status.sending': { en: 'Sending…', ne: 'पठाइँदै…' },
  'status.settingUp': { en: 'Setting up…', ne: 'सेटअप हुँदै…' },
  'status.uploadChecking': { en: 'Checking upload…', ne: 'अपलोड जाँच गर्दै…' },
  'status.openingMic': { en: 'Opening microphone…', ne: 'माइक खोल्दै…' },
  'status.roomTooLoud': {
    en: 'Room is too noisy ({level} dBFS, need below {limit}) — turn off fans/AC/TV and close doors/windows, then try again.',
    ne: 'कोठाको आवाज धेरै छ ({level} dBFS, चाहिने {limit} भन्दा कम) — पंखा, AC, TV बन्द गर्नुहोस् र झ्याल–ढोका थुन्नुहोस्, अनि फेरि प्रयास गर्नुहोस्।',
  },
  'status.recording': { en: 'Recording… read the sentence.', ne: 'रेकर्ड हुँदैछ… वाक्य पढ्नुहोस्।' },
  'status.goodListenSend': { en: 'Sounds good. Listen, then send.', ne: 'राम्रो छ। सुनेर पठाउनुहोस्।' },
  'status.savedListenConfirm': {
    en: 'Saved ✓ — you can listen above to confirm.',
    ne: 'सुरक्षित भयो ✓ — माथि सुनेर पक्का गर्न सक्नुहुन्छ।',
  },
  'error.configLoadFailed': { en: 'Could not load settings: {error}', ne: 'सेटिङ लोड हुन सकेन: {error}' },
  'error.unsupportedBrowser': {
    en: 'This browser does not support recording — use Chrome or Firefox.',
    ne: 'यो ब्राउजरले रेकर्डिङ समर्थन गर्दैन — Chrome वा Firefox प्रयोग गर्नुहोस्।',
  },
  'error.httpsRequired': { en: 'Microphone access requires HTTPS.', ne: 'माइक चलाउन HTTPS चाहिन्छ।' },
  'error.sendFailed': { en: 'Could not submit: {error}', ne: 'पठाउन सकिएन: {error}' },
  'error.micOpenFailed': { en: 'Could not open microphone: {error}', ne: 'माइक खोल्न सकिएन: {error}' },
  'error.uploadFailed': { en: 'Upload failed ({status})', ne: 'अपलोड असफल ({status})' },
  'error.workletSilent': {
    en: 'Microphone opened but no audio is coming in. This is not your fault — it’s a device/browser issue. Use Chrome if possible, or email hello@cloudfrm.ai. (AUDIO_WORKLET_SILENT)',
    ne: 'माइक खुल्यो तर आवाज आइरहेको छैन। यो तपाईंको गल्ती होइन — यो यन्त्र/ब्राउजरको समस्या हो। सम्भव भए Chrome प्रयोग गर्नुहोस्, नभए hello@cloudfrm.ai मा खबर गर्नुहोस्। (AUDIO_WORKLET_SILENT)',
  },

  // --- storage preflight (preflight.js) -----------------------------------------
  'preflight.cors': {
    en: 'There is a problem with the server’s setup — this is not your internet’s fault. Please email hello@cloudfrm.ai. Recording is unavailable right now.',
    ne: 'सर्भरको सेटिङमा समस्या छ — यो तपाईंको इन्टरनेटको समस्या होइन। कृपया hello@cloudfrm.ai मा खबर गर्नुहोस्। अहिले रेकर्ड गर्न मिल्दैन।',
  },
  'preflight.auth': {
    en: 'There is a permissions problem on the server — this is not your fault. Please email hello@cloudfrm.ai.',
    ne: 'सर्भरको अनुमतिमा समस्या छ — यो तपाईंको गल्ती होइन। कृपया hello@cloudfrm.ai मा खबर गर्नुहोस्।',
  },
  'preflight.network': {
    en: 'No internet connection. Check your connection and try again.',
    ne: 'इन्टरनेट जोडिएन। सम्पर्क जाँचेर फेरि प्रयास गर्नुहोस्।',
  },
  'preflight.unknown': {
    en: 'Upload check failed. Try again, or email hello@cloudfrm.ai.',
    ne: 'अपलोड जाँच असफल भयो। फेरि प्रयास गर्नुहोस्, नभए hello@cloudfrm.ai मा खबर गर्नुहोस्।',
  },

  // --- accounts (auth.js) ---------------------------------------------------------
  'auth.signIn': { en: 'Sign in', ne: 'साइन इन' },
  'auth.signInSubmit': { en: 'Sign in', ne: 'साइन इन गर्नुहोस्' },
  'auth.password': { en: 'Password', ne: 'पासवर्ड' },
  'auth.signUpTab': { en: 'Open an account', ne: 'खाता खोल्नुहोस्' },
  'auth.myRecordings': { en: 'My profile', ne: 'मेरो प्रोफाइल' },
  'auth.signOut': { en: 'Sign out', ne: 'साइन आउट' },
  'auth.account': { en: 'Account', ne: 'खाता' },
  'auth.creatingAccount': { en: 'Opening account…', ne: 'खाता खोलिँदै…' },
  'auth.signingIn': { en: 'Signing in…', ne: 'साइन इन हुँदै…' },
  'auth.checkEmail': {
    en: 'A confirmation link has been emailed — click it to come back.',
    ne: 'इमेलमा पुष्टिकरण लिङ्क पठाइएको छ — त्यहाँ क्लिक गरेर फर्कनुहोस्।',
  },
  'auth.errorBadCredentials': { en: 'Email or password did not match.', ne: 'इमेल वा पासवर्ड मिलेन।' },
  'auth.errorAlreadyRegistered': {
    en: 'An account with this email already exists — try signing in instead.',
    ne: 'यो इमेलमा खाता पहिल्यै छ — साइन इन प्रयास गर्नुहोस्।',
  },
  'auth.errorGoogleDisabled': { en: 'Google sign-in is not enabled right now.', ne: 'Google साइन इन अहिले सक्रिय छैन।' },
  'auth.errorGeneric': { en: 'Something went wrong, please try again.', ne: 'असफल भयो, फेरि प्रयास गर्नुहोस्।' },
  'auth.googleContinue': { en: 'Continue with Google', ne: 'Google बाट जारी राख्नुहोस्' },
  'auth.orDivider': { en: 'or', ne: 'वा' },
  'auth.footnote': {
    en: 'You can record without signing in. If you sign in, your recordings are linked to your account, so you can find them again later.',
    ne: 'साइन इन नगरी पनि रेकर्ड गर्न सकिन्छ। साइन इन गर्नुभयो भने तपाईंको रेकर्डिङहरू तपाईंको खातासँग जोडिन्छन्, ताकि पछि पनि हेर्न सकिन्छ।',
  },
  'auth.close': { en: 'Close', ne: 'बन्द गर्नुहोस्' },

  // --- profile page ---------------------------------------------------------
  'profilePage.signInHeading': { en: 'Sign in to see your profile', ne: 'आफ्नो प्रोफाइल हेर्न साइन इन गर्नुहोस्' },
  'profilePage.signInLede': {
    en: 'Your profile shows the details and recordings linked to your account.',
    ne: 'तपाईंको प्रोफाइलमा तपाईंको खातासँग जोडिएका विवरण र रेकर्डिङहरू देखिन्छन्।',
  },
  'profilePage.emptyHeading': { en: 'No recordings yet', ne: 'अहिलेसम्म कुनै रेकर्डिङ छैन' },
  'profilePage.emptyLede': {
    en: 'Once you record something on this account, your details and recordings will show up here.',
    ne: 'यो खातामा केही रेकर्ड गरेपछि, तपाईंको विवरण र रेकर्डिङहरू यहाँ देखिनेछन्।',
  },
  'profilePage.startRecording': { en: 'Start recording', ne: 'रेकर्डिङ सुरु गर्नुहोस्' },
  'profilePage.heading': { en: 'My profile', ne: 'मेरो प्रोफाइल' },
  'profilePage.detailsHeading': { en: 'Personal details', ne: 'व्यक्तिगत विवरण' },
  'profilePage.saveChanges': { en: 'Save changes', ne: 'परिवर्तनहरू सुरक्षित गर्नुहोस्' },
  'profilePage.saved': { en: 'Saved ✓', ne: 'सुरक्षित भयो ✓' },
  'profilePage.recordingsHeading': { en: 'My recordings', ne: 'मेरा रेकर्डिङहरू' },
  'profilePage.noClipsYet': { en: 'No recordings yet.', ne: 'अहिलेसम्म कुनै रेकर्डिङ छैन।' },
  'profilePage.listen': { en: 'Listen', ne: 'सुन्नुहोस्' },
  'profilePage.statusPassed': { en: 'Saved ✓', ne: 'सुरक्षित ✓' },
  'profilePage.statusFailed': { en: 'Not used (quality check)', ne: 'प्रयोग भएन (गुणस्तर जाँच)' },
  'profilePage.statusPending': { en: 'Processing…', ne: 'प्रक्रियामा…' },
};

function readStoredLang() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === 'en' || stored === 'ne' ? stored : null;
  } catch (_) {
    return null;
  }
}

let currentLang = readStoredLang() || DEFAULT_LANG;
const listeners = [];

export function getLang() {
  return currentLang;
}

export function setLang(lang) {
  if (lang !== 'en' && lang !== 'ne') return;
  currentLang = lang;
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch (_) {
    /* private browsing / storage disabled -- language just won't persist */
  }
  document.documentElement.lang = lang;
  listeners.forEach((fn) => fn(lang));
}

/** Call again after language changes, to re-render dynamic text. */
export function onLangChange(fn) {
  listeners.push(fn);
}

export function t(key, params) {
  const entry = STRINGS[key];
  if (!entry) {
    console.warn('[i18n] missing key', key);
    return key;
  }
  let text = entry[currentLang] ?? entry[DEFAULT_LANG];
  if (params) {
    for (const [name, value] of Object.entries(params)) {
      text = text.replaceAll(`{${name}}`, value);
    }
  }
  return text;
}

/** Apply t() to every [data-i18n] / [data-i18n-placeholder] element in root. */
export function applyStaticTranslations(root = document) {
  root.querySelectorAll('[data-i18n]').forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  root.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  root.querySelectorAll('[data-i18n-aria-label]').forEach((el) => {
    el.setAttribute('aria-label', t(el.dataset.i18nAriaLabel));
  });
  document.title = t('meta.title');
}

export function initLangSelector(selectId = 'lang-select') {
  const select = document.getElementById(selectId);
  if (!select) return;
  select.value = getLang();
  select.addEventListener('change', () => setLang(select.value));
}

document.documentElement.lang = currentLang;
