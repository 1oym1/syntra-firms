# Which fires we count (and which we drop)

Part of Step 3 (data cleaning). Arabic version: [below](#النسخة-العربية).

We keep only hotspots with **`type = 0`**, which FIRMS calls **"presumed vegetation fire"**. This is what the challenge is about: burning activity on natural and farmed land.

## What `type = 0` includes

| Source | In Sudan |
| --- | --- |
| **Savanna and grass fires** | The largest source. Found across the savanna belt (Darfur, Kordofan, Blue Nile), mostly in the dry season, roughly October to March |
| **Crop residue burning** | Burning sorghum and sugarcane residue after harvest, for example around Gezira and Sennar |
| **Land clearing** | Burning to clear land before planting or for grazing |
| **Forest fires** | Relatively few in Sudan |

## What we drop, and why

| Type | Meaning | Why we drop it |
| --- | --- | --- |
| `type = 1` | Active volcano | Not a fire |
| `type = 2` | Static land source (gas flares, refineries, factories) | Burns every day in the same place, which inflates counts and distorts the seasonal pattern |
| `type = 3` | Offshore | Same problem (oil platforms) |

## Three things to keep in mind

1. **"Presumed" matters.** `type = 0` means "not a volcano and not a known static source", not "certainly a vegetation fire". It can occasionally include a building or facility fire. In Sudan, conflict-related burning after 2023 (such as burned villages) is usually still recorded as `type = 0`. It may show up as an anomaly in the calendar, which is an important story for emergency responders. Present it as a possible explanation, not a confirmed fact.

2. **The `type` field exists only in the archive.** The yearly files up to 2025 include `type`, but **2026 near-real-time (NRT) data from the API does not**. To compare the current month with history, we build our own **static-source mask** from the archive: grid cells that were classified `type = 2`, or that have fire on more than 50% of the days in a year. Any new hotspot in those cells is dropped. This keeps cleaning identical for archive and live data.

3. **Sudan loses very little data.** According to `outputs/tables/country_screen_modis_2025.csv`, `type = 0` makes up about 99% of hotspots in most African countries, so this filter removes only a small share. Saudi Arabia and Iraq are different: flares are a large part of their data, which is exactly why they are the "hard case".

**In short:** we work on savanna and farm fires in Sudan and drop every fixed heat source.

---

<div dir="rtl">

## النسخة العربية

نعتمد على النقاط من **`type = 0`**، واسمها الرسمي في FIRMS **"presumed vegetation fire"**، يعني حرائق غطاء نباتي مفترضة. وهذا هو موضوع التحدي أصلاً: نشاط الحرائق في الطبيعة والأراضي.

### وش يدخل في `type = 0`

| المصدر | في السودان |
| --- | --- |
| **حرائق السافانا والحشائش** | المصدر الأكبر. تنتشر في حزام السافانا في دارفور وكردفان والنيل الأزرق، وتكثر في موسم الجفاف تقريباً من أكتوبر إلى مارس |
| **حرق المخلفات الزراعية** | حرق بقايا الذرة الرفيعة وقصب السكر بعد الحصاد، مثلاً في مناطق الجزيرة وسنار |
| **إزالة الأراضي** | تنظيف الأرض بالحرق قبل الزراعة أو للرعي |
| **حرائق الغابات** | قليلة نسبياً في السودان |

### وش نحذف ولماذا

| النوع | المعنى | سبب الحذف |
| --- | --- | --- |
| `type = 1` | بركان نشط | ما هو حريق |
| `type = 2` | مصدر ثابت على اليابسة (مشاعل غاز، مصافي، مصانع) | يشتعل كل يوم في نفس المكان، فيرفع العدد بشكل وهمي ويخرّب الموسمية |
| `type = 3` | منصات بحرية | نفس المشكلة (منصات نفط) |

### ثلاث نقاط لازم نعرفها

1. **كلمة "مفترض" لها معنى.** `type = 0` يعني "مو بركان ومو مصدر ثابت معروف"، وما يعني إنه أكيد حريق نباتي. فممكن يدخل فيه أحياناً حريق مبنى أو منشأة. وفي السودان بالذات، الحرائق المرتبطة بالنزاع بعد 2023، مثل حرق القرى، تنسجل غالباً `type = 0` بعد. هذا ممكن يطلع كـ "شذوذ" في التقويم، وهو قصة مهمة للمستجيبين للطوارئ، فنذكره في العرض كتفسير محتمل، مو كحقيقة مؤكدة.

2. **حقل `type` موجود في بيانات الأرشيف بس.** الملفات السنوية لحد 2025 فيها `type`، لكن **بيانات 2026 من الـ API (NRT) ما فيها هذا الحقل**. فعشان مقارنة الشهر الحالي بالتاريخ، نحتاج **قناع مصادر ثابتة** نبنيه بنفسنا من بيانات الأرشيف: نحدد الخلايا اللي صُنّفت `type = 2` في الأرشيف، أو اللي فيها حرائق في أكثر من 50% من أيام السنة، ونحذف أي نقطة جديدة تطيح فيها. كذا التنظيف يكون واحد للأرشيف والبيانات الحية.

3. **ما راح نخسر بيانات كثير في السودان.** حسب `outputs/tables/country_screen_modis_2025.csv`، نسبة `type = 0` في أغلب الدول الأفريقية تقريباً 99%، يعني الحذف يشيل نسبة صغيرة. الوضع مختلف في السعودية والعراق، لأن المشاعل هناك نسبة كبيرة من البيانات، وهذا بالضبط اللي يخليهم "حالة صعبة".

**الخلاصة:** نشتغل على حرائق السافانا والزراعة في السودان، ونحذف كل مصدر حراري ثابت.

</div>
