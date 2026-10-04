# ExerLink — Dashboard 

**กลุ่มอุตสาหกรรม:** กลุ่มอุตสาหกรรมการจัดการเพื่อสิ่งแวดล้อม  
**รายวิชา:** Data WareHouse

ExerLink คือแพลตฟอร์มจับคู่ของเสียและความร้อนเหลือทิ้งภายในนิคมอุตสาหกรรม 

> ⚠️ ตัวเลขทั้งหมดเป็น **ข้อมูลจำลอง** เพื่อการออกแบบ ยังไม่ใช่ข้อมูลจริงของโรงงานหรือนิคมฯ ใด

## งานที่ส่ง

| หัวข้อที่ต้องส่ง | ไฟล์ |
|---|---|
| Dashboard (1 หน้า เชิงเล่าเรื่อง) | [`index.html`](index.html) |
| Data ที่ใช้ | [`data/`](data/) — xlsx + CSV ทำตาม Dashboard Brief Canvas |
| ผู้จัดทำ | (#นายปัณณกร พลเสน 67160352) |
| Repository | repo นี้ |

เอกสารประกอบ:
- [`docs/dashboard-brief-canvas.md`](docs/dashboard-brief-canvas.md) — Brief canvas, wireframe, เหตุผลที่เลือก chart, กฎ alert
- [`docs/presentation-script.md`](docs/presentation-script.md) — บทนำเสนอ 3 นาที
- [`docs/bmc.md`](docs/bmc.md) — Business Model Canvas (ตาราง)
- [`docs/ExerLink_Business_Model.pdf`](docs/ExerLink_Business_Model.pdf) — BMC, SWOT, 4M, 4P, Branding ฉบับเต็ม

## เรื่องที่ dashboard เล่า

> ลูกค้าลดค่ากำจัดได้ **14.4%** ผ่านเป้า 10% แล้ว แต่ **6 ใน 9 โรงงานที่ทดลองครบยังไม่ต่อสมาชิก** ทั้งที่ 5 รายประหยัดได้เกินเป้า

หน้าเดียวอ่านจากบนลงล่าง: ตัวกรอง + Dashboard Brief → สรุปประจำเดือน → KPI 5 ตัว → 01 ผลลัพธ์ (กราฟเส้นเทียบเป้า) → 02 สาเหตุ (รายโรงงาน / รายชนิดของเสีย) → 03 สิ่งที่ต้องดำเนินการ

**การโต้ตอบ:** กรองตามเดือน ขนาดโรงงาน S/M/L และชนิดของเสีย (ทุกส่วนคำนวณใหม่จากตาราง Fact) · กดจุดในกราฟเพื่อเลือกเดือน · สลับมุมมองรายโรงงาน/รายชนิดของเสีย และกดแถบเพื่อกรองทั้งหน้า · กรองตามสถานะลูกค้า · กดหัวข้อ Brief ทั้ง 6 ช่องเพื่อไฮไลต์ส่วนที่ตอบหัวข้อนั้น · กดมอบหมายงานในรายการที่ต้องดำเนินการ

## ข้อมูล (ทำตาม Dashboard Brief Canvas)

| ไฟล์ | บทบาทใน canvas | คอลัมน์ |
|---|---|---|
| `fact_factory_stream_month.csv` | **Grain**: 1 แถว = โรงงาน × ชนิดของเสีย × เดือน (132 แถว) | `month, factory_id, stream_id, tons_listed, tons_diverted, tons_landfill, cost_saved_thb, kgco2e_reduced, deals_closed` |
| `dim_factory.csv` | **Dimension**: โรงงาน 12 แห่ง | `factory_id, industry, size, join_month, baseline_cost_thb_per_month, status, member_since, trial_days_left, streams` |
| `dim_stream.csv` | **Dimension**: ชนิดของเสีย 7 ชนิด | `stream_id, name, waste_code, receiver_license, receiver, match_start_month` |
| `revenue_quarter.csv` | รายได้ตาม 5 ช่องทางใน BMC | `stream, Q1_2569, Q2_2569, Q3_2569` |
| `ExerLink_Dashboard_Data.xlsx` | ทุกตารางด้านบน + ชีต `Brief_Canvas` + ชีต `Monthly` (**Metric** คำนวณด้วย SUMIFS จาก Fact) | — |

สมมติฐาน: ค่ากำจัดเดิมตามขนาดโรงงาน S 55,000 / M 90,000 / L 165,000 บาทต่อเดือน
แหล่งข้อมูลจริงที่จะใช้แทน: ทะเบียนโรงงาน DIW, gdcatalog, ค่า EF ของ TGO, ใบรับของเสียและใบแจ้งหนี้จากผู้รับกำจัด

## วิธีเปิด

เปิด `index.html` ในเบราว์เซอร์ได้ทันที (ฟอนต์โหลดจาก Google Fonts) หรือเปิด GitHub Pages: Settings → Pages → Deploy from branch → `main` / root

## โครงสร้าง

```
exerlink-dashboard/
├── index.html                         Dashboard 1 หน้า
├── data/
│   ├── ExerLink_Dashboard_Data.xlsx
│   ├── fact_factory_stream_month.csv
│   ├── dim_factory.csv
│   ├── dim_stream.csv
│   └── revenue_quarter.csv
└── docs/
    ├── dashboard-brief-canvas.md
    ├── presentation-script.md
    ├── bmc.md
    └── ExerLink_Business_Model.pdf
```

## ผู้จัดทำ
| Pannakorn Polasen | 67160352 |
