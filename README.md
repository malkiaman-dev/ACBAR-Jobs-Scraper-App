# 💼 ACBAR Jobs Scraper App

A Python-based web scraping application built to extract job listings and opportunities from the **ACBAR Jobs Portal** automatically.

This tool helps users collect and organize job data for:

* Job hunting
* Recruitment analysis
* Market research
* Automated job monitoring

---

## 🚀 Overview

The **ACBAR Jobs Scraper App** automates the process of scraping jobs from the ACBAR website.

It can:

1. Visit the ACBAR jobs portal
2. Extract available job listings
3. Collect detailed job information
4. Save results in structured files
5. Prevent duplicate entries

---

## ✨ Features

### 🔍 Job Listing Extraction

Extracts information such as:

* Job title
* Company / organization name
* Location
* Job category
* Deadline / closing date
* Job details URL

---

### 📄 Detailed Job Information

Can collect additional data like:

* Job description
* Requirements
* Qualifications
* Salary / benefits (if available)

---

### ♻️ Duplicate Prevention

Prevents saving duplicate job listings across runs.

---

### 💾 Export Support

Save scraped jobs in formats like:

* CSV
* JSON
* Excel (if implemented)

---

### 🖥️ App Interface

Includes a user-friendly application interface for easier usage.

---

## 🛠️ Tech Stack

Built with:

* **Python**
* **Selenium / BeautifulSoup / Requests** (depending on implementation)
* **Pandas**
* **Tkinter / CustomTkinter / Streamlit / Flask** (depending on app UI)

---

## 📁 Project Structure

```bash id="u3m4jq"
acbar_scraper_app/
│
├── main.py / app.py
├── scraper/
├── outputs/
├── requirements.txt
└── README.md
```

---

## ⚙️ Installation

Clone repository:

```bash id="h7r8tp"
git clone <your-repo-url>
cd acbar_scraper_app
```

Install dependencies:

```bash id="g6m1zc"
pip install -r requirements.txt
```

---

## ▶️ Usage

Run the application:

```bash id="l4y7vd"
python app.py
```

or

```bash id="c9q3ak"
python main.py
```

---

## 📊 Output Example

Example job record:

| Title             | Organization | Location | Deadline   |
| ----------------- | ------------ | -------- | ---------- |
| Software Engineer | XYZ NGO      | Kabul    | 2026-05-01 |

---

## ⚠️ Notes

* Website structure changes may require updates
* Scraping speed depends on internet and website response
* Respect website terms of service

---

## 🚀 Future Improvements

Possible upgrades:

* Auto-scheduled scraping
* Email notifications for new jobs
* Advanced filtering
* Cloud deployment

---

## 💡 Author

Developed by **Malki Aman**.
