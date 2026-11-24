from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import json
import re
import zipfile
from openai import OpenAI
import os

app = FastAPI()
# --- АГЕНТ-РЕВЬЮЕР ---
def review_html(html_code):
    try:
        prompt = f"""Ты строгий QA-инженер. Проверь этот HTML-код на грубые ошибки:
        1. Есть ли незакрытые теги (например, открыт <div>, а закрывающего </div> нет)?
        2. Есть ли битые ссылки в меню?
        Если код идеален, напиши ровно одно слово: "ОК".
        Если есть ошибки, напиши их кратким списком.
        
        Код: {html_code}"""
        
        response = client.chat.completions.create(
            model="deepseek/deepseek-v4-flash",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Ошибка проверки: {e}"
# ---------------------
API_KEY = os.getenv("OPENAI_API_KEY") # <-- ВСТАВЬ СВОЙ КЛЮЧ!
client = OpenAI(api_key=API_KEY, base_url="https://api.provod.ai/v1")

@app.get("/")
def read_root():
    return FileResponse("form.html")

@app.get("/site/{page_name}")
def read_site(page_name: str = "index"):
    try:
        return FileResponse(f"{page_name}.html")
    except:
        return HTMLResponse("Страница не найдена", status_code=404)

@app.get("/download")
def download_zip():
    return FileResponse("website.zip", media_type="application/zip", filename="my_website.zip")

@app.post("/generate")
def generate_from_form(
    topic: str = Form(...),
    style: str = Form(...),
    colors: str = Form(...),
    audience: str = Form(...),
    pages: str = Form(...)
):
    page_list = [p.strip() for p in pages.split(",")]
    pages_mapping = []
    for i, p in enumerate(page_list):
        filename = "index" if i == 0 else f"page_{i}" 
        pages_mapping.append({"filename": filename, "title": p})
    
    # ПРОСИМ НЕЙРОСЕТЬ СДЕЛАТЬ МЕНЮ
    prompt = f"""Ты профессиональный веб-разработчик. Создай многостраничный сайт на тему: '{topic}'.
    Стиль: {style}. Цвета: {colors}. Аудитория: {audience}.
    
    Твоя задача — сгенерировать HTML-код для каждой страницы и ОБЩИЙ CSS.
    ВАЖНО: В каждую страницу ты ОБЯЗАН вставить навигационное меню (тег <nav>), чтобы между страницами можно было переключаться.
    В меню должны быть ссылки на ВСЕ созданные страницы. Используй ОТНОСИТЕЛЬНЫЕ ссылки (например, <a href="index.html">Главная</a>, <a href="page_1.html">...</a>).
    
    Вот список страниц и их точные имена файлов, которые нужно использовать в ссылках:
    {json.dumps(pages_mapping, ensure_ascii=False)}
    
    Верни ответ СТРОГО в формате JSON (без markdown-разметки ```json):
    {{
        "css": "Общий CSS-код для всех страниц, включая стили для меню навигации",
        "pages": [
            {{"filename": "index", "html": "HTML-код главной (с меню)"}},
            {{"filename": "page_1", "html": "HTML-код второй страницы (с меню)"}}
        ]
    }}
    """

    try:
        response = client.chat.completions.create(
            model="deepseek/deepseek-v4-flash",
            messages=[{"role": "user", "content": prompt}]
        )
        raw_response = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw_response)
        if not isinstance(data, dict):
            raise ValueError("Нейросеть вернула текст вместо словаря...")
        
        pages_data = data.get('pages', [])

        # Ревьюер
        print("\n--- 🕵️‍♂️ АГЕНТ-РЕВЬЮЕР ПРОВЕРЯЕТ КОД ---")
        for p in pages_data:
            print(f"Проверяю страницу: {p['filename']}.html...")
            review_result = review_html(p['html'])
            print(f"Вердикт: {review_result}")
        print("--- ПРОВЕРКА ЗАВЕРШЕНА ---\n")

        # Сохраняем CSS
        with open("style.css", "w", encoding="utf-8") as f:
            f.write(data.get('css', ''))
            
        # СОХРАНЯЕМ СТРАНИЦЫ
        for p in pages_data:
            filename = f"{p['filename']}.html"
            
            # 1. Чистим ссылки для ZIP
            clean_html = p['html'].replace('href="/', 'href="').replace("href='/", "href='")
            
            # 2. ПРОВЕРКА: Есть ли меню от нейросети? (ищем тег nav)
            if "<nav" not in clean_html.lower():
                print(f"⚠️ Нейросеть забыла меню для {filename}. Вставляем страховочное.")
                # Страховочное меню на Python
                nav_links = "".join([f'<a href="{m["filename"]}.html" style="color: #333; text-decoration: none; padding: 10px 15px; font-weight: bold;">{m["title"]}</a>' for m in pages_mapping])
                fallback_nav = f'<nav style="background: rgba(255,255,255,0.8); padding: 15px; text-align: center; border-bottom: 1px solid #ccc;">{nav_links}</nav>'
                clean_html = fallback_nav + clean_html
            else:
                print(f"✅ Нейросеть сделала меню для {filename}. Оставляем как есть.")

            with open(filename, "w", encoding="utf-8") as f:
                html_template = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{topic}</title>
    <link rel="stylesheet" href="style.css">
</head>
<body style="margin: 0; padding: 0;">
    {clean_html}
</body>
</html>"""
                f.write(html_template)
                
        # ZIP
        with zipfile.ZipFile("website.zip", "w") as zip_file:
            zip_file.write("style.css")
            for p in pages_data:
                zip_file.write(f"{p['filename']}.html")

        links_html = "".join([f'<a href="/site/{p["filename"]}" target="_blank" style="display:block; margin:10px; color:#4CAF50; font-size:18px;">Посмотреть {p["filename"]}.html</a>' for p in pages_data])
        
        return HTMLResponse(content=f"""
        <html><body style="background:#121212; color:white; text-align:center; padding-top:50px; font-family:Arial;">
        <h1>✅ Сайт с навигацией создан!</h1>
        <div style="margin-bottom: 30px;">{links_html}</div>
        <a href="/download" style="display:inline-block; padding:15px 30px; background:#1E90FF; color:white; text-decoration:none; border-radius:5px; font-size:20px; font-weight:bold;">📦 Скачать сайт (ZIP)</a>
        <br><br><br>
        <a href="/" style="color:#aaa;">Сгенерировать еще один</a>
        </body></html>
        """)

    except json.JSONDecodeError:
        return HTMLResponse(content="<h1 style='color:red; text-align:center;'>❌ Ошибка нейросети (сломан JSON). Попробуйте еще раз.</h1><div style='text-align:center;'><a href='/'>Назад</a></div>", status_code=500)
    except Exception as e:
        return HTMLResponse(content=f"<h1 style='color:red; text-align:center;'>⚠️ Ошибка: {e}</h1><div style='text-align:center;'><a href='/'>Назад</a></div>", status_code=500)