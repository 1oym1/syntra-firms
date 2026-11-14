# MODIS vs VIIRS: what they are, how they differ, how we harmonize them

One-page PDF version (English + Arabic): [MODIS_vs_VIIRS.pdf](MODIS_vs_VIIRS.pdf). Arabic version of this page: [below](#النسخة-العربية).

## What are MODIS and VIIRS?

MODIS and VIIRS are scientific imaging sensors carried on satellites that orbit the Earth. They image the planet at several wavelengths, including thermal infrared, which is what lets them detect fires: any spot much hotter than its surroundings is recorded as a fire **hotspot**.

**MODIS** (Moderate Resolution Imaging Spectroradiometer)
- NASA's older-generation sensor, flying on two satellites: Terra (since 2000) and Aqua (since 2002).
- Sees the ground in pixels of about 1 km, so it can miss small fires.
- Its big advantage is the **longest historical record**: more than 25 years.
- Its satellites are old and are expected to stop operating in 2027.

**VIIRS** (Visible Infrared Imaging Radiometer Suite)
- The newer generation that succeeds MODIS, flying on Suomi NPP (since 2012), NOAA-20 and NOAA-21.
- Its pixels are about 375 m, so it sees much finer detail and catches small fires MODIS misses.
- Its record is shorter: it starts only in 2012.

**A simple analogy.** Picture two cameras filming the same neighbourhood. One is old and low-resolution but has footage going back 25 years. The other is new and sharp but only has 13 years of footage. If you count the "lights on" in the new camera's images you will find many more. The lights did not increase; the camera just sees more.

**That is our challenge.** We want both the long MODIS history and the fine VIIRS detail, so we merge them into one consistent series. Then, when fire counts go up, we know the rise is real and not an artefact of switching sensors. All the data is free from NASA FIRMS.

## Technical comparison

| Property | MODIS | VIIRS (375 m I-band) |
| --- | --- | --- |
| Satellites | Terra (Nov 2000), Aqua (Jul 2002) | Suomi NPP (2012), NOAA-20 (2018), NOAA-21 (2023) |
| Fire pixel at nadir | 1 km | 375 m (about 7× more pixels per area) |
| Pixel at swath edge | Grows to about 2 × 4.8 km | Only about 0.8 × 0.8 km (on-board aggregation) |
| Swath width | About 2,330 km | About 3,060 km, no gaps between orbits |
| Overpass (local time) | Terra 10:30 / 22:30; Aqua 13:30 / 01:30 | All three 13:30 / 01:30 |
| Detection sensitivity | Lower; misses small and cool fires | Much higher; small farm fires, more night fires |
| `confidence` field | Numeric 0–100 | Categorical `l` / `n` / `h` |
| Brightness field | `brightness` (band 21, 4 µm) | `bright_ti4` (band I4) |
| FRP | Available | Available; smaller per-pixel values |
| Sensor saturation | Rare | Band I4 saturates on intense fires (affects FRP) |

## What this means for our project

> **Do not compare raw counts.** For the same area and period, VIIRS typically records 3 to 10 times as many hotspots as MODIS. If the two are simply added together in the calendar, a false "jump" will appear in 2012.

**Our 2025 data confirms this** ([`outputs/tables/sensor_agreement_2025.csv`](../outputs/tables/sensor_agreement_2025.csv), vegetation fires): across 112 countries the VIIRS/MODIS ratio ranges from 2.7× to 11.7× (median 4.9×). **Saudi Arabia: about 10×** (16,715 vs 1,677), with low agreement (ratio CV 0.28, 5 active months), so one global factor will not work here.

### Harmonization options (Step 4)

- **(a) Gridding:** count burned cells on a 1 km or 0.1° grid instead of counting points. Simple, and removes much of the resolution gap.
- **(b) Conversion factor from the overlap period (2012–present):** compute the VIIRS/MODIS ratio per month, region or land cover, then convert the 2000–2011 MODIS series into a "VIIRS-equivalent" (or the reverse).
- **(c) FRP harmonization:** sum fire radiative power instead of counting points. Physically the closest approach, but affected by saturation.

**Recommendation: (a) + (b) together.** Grid first, then fit a regression factor from the overlap period for each calendar month, then validate it with cross-validation on held-out years (Step 5).

### Data cleaning (Step 3)

Unify confidence, for example treat MODIS ≥ 30 as equivalent to VIIRS `n` and `h`. Drop `type ≠ 0` (volcanoes and static sources such as refineries and gas flares). This matters a lot in Saudi Arabia and the Gulf.

### Data continuity

FIRMS stopped producing new Suomi NPP fire data on 2 Nov 2026; use NOAA-20 / NOAA-21 for recent data. NASA projects end of science operations for Terra in Feb 2027 and Aqua in Sep 2027. A harmonized record keeps the 2000-onward history usable after MODIS retires.

Sources: [NASA Earthdata: Transitioning from Suomi NPP](https://www.earthdata.nasa.gov/news/blog/transitioning-from-s-npp-viirs-omps-what-nasa-firms-users-need-know), [NASA Science: Terra, The End of An Era](https://science.nasa.gov/?p=1183595), [FIRMS attribute definitions](https://www.earthdata.nasa.gov/data/tools/firms/active-fire-data-attributes-modis-viirs).

---

<div dir="rtl">

## النسخة العربية

### ما هو MODIS و VIIRS؟

**MODIS وVIIRS حساسات (كاميرات علمية) مركّبة على أقمار صناعية تدور حول الأرض.** تصوّر الأرض بأطوال موجية مختلفة، منها الأشعة تحت الحمراء الحرارية، وهذا اللي يخليها تكشف الحرائق: أي بقعة أسخن بكثير من اللي حولها تنسجل كـ "نقطة حريق" (hotspot).

**MODIS** (Moderate Resolution Imaging Spectroradiometer)
- الجيل القديم من ناسا، ويشتغل على قمرين: Terra من سنة 2000، وAqua من 2002.
- يشوف الأرض ببكسلات حجمها حوالي 1 كم، فالحرائق الصغيرة ممكن تفوته.
- ميزته الكبيرة إن عنده **أطول سجل تاريخي**، أكثر من 25 سنة.
- الأقمار اللي يشتغل عليها قديمة، ومتوقع تتوقف في 2027.

**VIIRS** (Visible Infrared Imaging Radiometer Suite)
- الجيل الأحدث اللي يخلف MODIS، ويشتغل على أقمار Suomi NPP (من 2012) وNOAA-20 وNOAA-21.
- بكسلاته حوالي 375 م، يعني يشوف تفاصيل أدق بكثير ويلقط حرائق صغيرة ما يشوفها MODIS.
- سجله أقصر، يبدأ من 2012 فقط.

**تشبيه بسيط:** تخيّل كاميرتين تصوّران نفس الحي. وحدة قديمة دقتها ضعيفة لكن عندها صور من 25 سنة، والثانية حديثة دقتها عالية لكن صورها من 13 سنة بس. لو عدّيت "الأنوار المشتعلة" في صور الكاميرا الحديثة، بتلقى عددها أكثر بكثير. هذا مو لأن الأنوار زادت، بل لأن الكاميرا صارت تشوف أكثر.

**وهذا بالضبط تحدينا:** نبي نستفيد من تاريخ MODIS الطويل ومن دقة VIIRS العالية، فلازم نوحّدهم في سلسلة وحدة متسقة. بكذا لما يظهر ارتفاع في عدد الحرائق، نعرف إنه حقيقي ومو مجرد أثر لتغيير الحساس. البيانات كلها متاحة مجاناً من NASA FIRMS.

### ماذا يعني هذا لمشروعنا

**لا تقارنوا الأعداد الخام.** في نفس المنطقة ونفس الفترة يسجّل VIIRS عادةً من 3 إلى 10 أضعاف عدد نقاط MODIS. لو جمعنا الاثنين مباشرة في التقويم ستظهر "قفزة" وهمية في 2012.

**بياناتنا لعام 2025 تؤكد ذلك:** في 112 دولة تتراوح النسبة VIIRS/MODIS بين 2.7 و11.7 ضعفاً (الوسيط 4.9). **السعودية: حوالي 10 أضعاف** (16,715 مقابل 1,677) مع توافق ضعيف، فلا يصلح معامل عالمي واحد هنا.

**خيارات المواءمة (الخطوة 4):**
- **(أ) التجميع الشبكي (Gridding):** نعدّ الخلايا المحترقة على شبكة 1 كم أو 0.1° بدل عدّ النقاط. بسيط ويزيل جزءاً كبيراً من فرق الدقة.
- **(ب) معامل تحويل من فترة التداخل (2012 حتى الآن):** نحسب النسبة VIIRS/MODIS لكل شهر أو منطقة أو غطاء أرضي، ثم نحوّل سلسلة MODIS للفترة 2000–2011 إلى "مكافئ VIIRS"، أو العكس.
- **(ج) مواءمة FRP:** نجمع طاقة الإشعاع الحراري بدل عدّ النقاط. الأقرب فيزيائياً، لكنه يتأثر بتشبّع الحساس.

**التوصية: (أ) + (ب) معاً.** نبني الشبكة أولاً، ثم نحسب معامل انحدار من فترة التداخل لكل شهر من السنة، ثم نتحقق منه بـ cross-validation على سنوات محجوبة (الخطوة 5).

**تنظيف البيانات (الخطوة 3):** نوحّد مستويات الثقة، فمثلاً نعتبر MODIS ≥ 30 مكافئاً لـ VIIRS `n` و`h`. ونحذف كل نقطة `type ≠ 0`، وهي البراكين والمصادر الثابتة مثل المصافي ومشاعل الغاز. هذه الخطوة مهمة جداً في السعودية والخليج.

**استمرارية البيانات:** توقف إنتاج بيانات Suomi NPP الجديدة في FIRMS يوم 2 نوفمبر 2026، فنستخدم NOAA-20 وNOAA-21 للبيانات الحديثة. وتتوقع ناسا انتهاء العمليات العلمية لـ Terra في فبراير 2027 ولـ Aqua في سبتمبر 2027.

</div>
