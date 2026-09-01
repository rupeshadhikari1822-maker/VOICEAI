# रेकर्डिङ निर्देशिका / Recording guide

तपाईंको आवाजको गुणस्तरले नै यो परियोजनाको नतिजा तय गर्छ। महँगो उपकरण चाहिँदैन —
**शान्त कोठा** र **ठीक दूरी** नै मुख्य कुरा हो।

---

## कोठा

| गर्नुहोस् | नगर्नुहोस् |
|---|---|
| सानो, नरम कोठा — ओछ्यान, पर्दा, दराज भएको | ठूलो खाली कोठा, भर्‍याङ, बाथरुम |
| झ्याल–ढोका बन्द | झ्याल खुला, सडकको आवाज भित्र |
| पंखा, AC, कुलर, फ्रिज, TV **निभाएको** | पंखा घुमिरहेको |
| एक्लै | अरू मानिस कुरा गरिरहेका |

**किन:** खाली कोठामा आवाज भित्ता–भित्तामा ठोक्किएर प्रतिध्वनि (echo) बन्छ। मोडेलले
त्यो प्रतिध्वनि पनि तपाईंको आवाजकै अंश हो भनेर सिक्छ, र नतिजा बिग्रिन्छ।

पंखाको आवाज तपाईंलाई सुनिँदैन, तर माइकले टिप्छ। यही कारण धेरै रेकर्डिङ अस्वीकृत हुन्छन्।

## फोन

फोन **साइलेन्ट** गर्नुहोस् — **भाइब्रेट होइन**। भाइब्रेटले टेबुलमा ठक्ठक् आवाज बनाउँछ,
जुन रेकर्डिङमा तीखो चट्को (impulse noise) भएर बस्छ र हटाउन सकिँदैन।

## माइक

1. **तार भएको हेडसेट सबैभन्दा राम्रो।** ल्यापटपको भित्रैको माइक भन्दा धेरै राम्रो।
2. **ब्लुटुथ नचलाउनुहोस्।** ब्लुटुथ हेडसेटले बोल्दा HFP मोडमा जान्छ, जसले आवाज
   ८ वा १६ kHz मोनोमा झार्छ। हामीलाई ४८ kHz चाहिन्छ। एप्ले ब्लुटुथ माइक पत्ता लगाए
   चेतावनी देखाउँछ।
3. **दूरी: मुखबाट १५–२० सेमी** (करिब एक बित्ता)।
4. **अलि छेउतिर राख्नुहोस्** — सिधै मुखअगाडि होइन। "प", "ब", "फ" बोल्दा निस्कने
   हावाको धक्का (plosive) सिधै माइकमा ठोक्किँदा "पप्" आवाज आउँछ।
5. **एउटै सत्रभरि उही माइक, उही दूरी, उही कोठा।** बीचमा फेरे एउटै वक्ताको आवाज
   फरक-फरक सुनिन्छ, र TTS मोडेल अस्थिर बन्छ।

## बोल्ने तरिका

- **स्वाभाविक गतिमा बोल्नुहोस्।** समाचार वाचक जसरी नपढ्नुहोस्, नाटक नगर्नुहोस्।
- बोल्न सुरु गर्नुअघि **आधा सेकेन्ड पर्खनुहोस्**। वाक्य सकिएपछि पनि **आधा सेकेन्ड**
  पर्खेर मात्र रोक्नुहोस्।
- वाक्यमा गल्ती भयो भने **फेरि रेकर्ड** गर्नुहोस् — बीचमा सच्याउन नखोज्नुहोस्।
- पर्दामा जे लेखिएको छ, **त्यही** पढ्नुहोस्। शब्द थप्ने वा हटाउने नगर्नुहोस्।
- घाँटी सुक्यो भने पानी पिउनुहोस्। थकाइ लाग्यो भने रोकेर पछि फर्कनुहोस्।

## प्रश्नवाचक वाक्य

`?` भएका वाक्यमा अन्त्यमा स्वर **माथि** जानुपर्छ। सपाट स्वरमा पढ्नुभयो भने
मोडेलले प्रश्नको लय सिक्न पाउँदैन।

---

## एपले के जाँच्छ

रेकर्डिङ अघि **माइक जाँच** हुन्छ: ५ सेकेन्ड चुप बस्नुहुन्छ, र एपले कोठाको आवाज
नाप्छ। **−50 dBFS भन्दा बढी** भयो भने अघि बढ्न दिँदैन।

हरेक वाक्य रेकर्ड गरेपछि यी नापिन्छन्:

| नाप | चाहिने | बिग्रिए के गर्ने |
|---|---|---|
| SNR | ≥ 30 dB (TTS: 40 dB) | पंखा/झ्याल बन्द, शान्त कोठा |
| स्तर (peak) | −6 देखि −3 dBFS | धेरै ठूलो भए माइक टाढा, सानो भए नजिक |
| कोठाको आवाज | < −50 dBFS | पृष्ठभूमिको आवाज हटाउनुहोस् |
| Clipping | < ०.०५ % | माइक टाढा सार्नुहोस् |
| अवधि | ४–१० सेकेन्ड | पूरा वाक्य, नअड्किई |
| सुरु/अन्त्यको चुप्पी | २००–५०० ms | बोल्नुअघि/पछि आधा सेकेन्ड पर्खनुहोस् |

अस्वीकृत भयो भने एपले **के गर्ने** भन्छ — कोड वा त्रुटि सन्देश देखाउँदैन। जे भन्छ
त्यही गरेर फेरि रेकर्ड गर्नुहोस्।

---

## English summary

Quality comes from a quiet room and correct mic distance, not expensive gear.

**Room:** small and soft (bedroom with curtains beats an empty hall). Windows and
doors closed. Fan, AC, cooler and TV off — you stop hearing a fan after a minute,
but the microphone never does, and it is the most common cause of rejected clips.

**Phone on silent, not vibrate.** Vibration against a desk becomes impulse noise
that cannot be removed afterwards.

**Mic:** a wired headset beats a laptop's built-in mic. **Bluetooth is rejected** —
headsets switch to HFP when the mic opens, which resamples to 8/16 kHz mono, and
the app warns you if it detects one. Keep it 15–20 cm from your mouth and slightly
off-axis so plosives don't hit the capsule. Use the same room, mic and distance
for every session by one speaker; changing them mid-corpus makes one voice sound
like several and destabilises a TTS model.

**Delivery:** natural pace, not a newsreader. Pause ~0.5 s before starting and
after finishing. Re-record rather than correcting mid-sentence. Read exactly what
is on screen. Let question marks rise at the end.

The mic check measures your room tone over 5 seconds of silence and blocks you
above −50 dBFS. Each take is then gated on SNR, peak level, clipping, duration
and silence padding. Rejections tell you what to physically change, not what the
code did.
