import os
import json
import re
from collections import Counter
from io import BytesIO

from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


# -----------------------------
# CONFIG
# -----------------------------

PRODUCTS_JSON = "products2.json"

# productos que NO definen agrupación
SECONDARY_PRODUCTS = [
    "PRODUCTO REGALO HOMBRE",
    "PRODUCTO REGALO MUJER",
    "PRODUCTO REGALO NIÑOS",
    "PRODUCTO REGALO NIÑAS"
]


# -----------------------------
# Cargar productos
# -----------------------------

with open(PRODUCTS_JSON, "r", encoding="utf-8") as f:
    products_data = json.load(f)

product_map = {}
product_names = []

for key, value in products_data.items():

    name = value["name"].upper()

    product_map[name] = value
    product_names.append(name)


# -----------------------------
# Buscar PDFs en carpeta
# -----------------------------

current_folder = os.getcwd()

pdf_files = [f for f in os.listdir(current_folder) if f.lower().endswith(".pdf")]

if not pdf_files:
    print("No se encontraron PDFs en la carpeta.")
    exit()


# -----------------------------
# Procesar cada PDF
# -----------------------------

for pdf_file in pdf_files:

    print(f"\nProcesando: {pdf_file}")

    reader = PdfReader(pdf_file)

    pages_data = []
    product_counts = Counter()

    # -----------------------------
    # Analizar páginas
    # -----------------------------

    for i, page in enumerate(reader.pages):

        text = page.extract_text()

        if not text:
            continue

        text = text.upper()

        # arreglar palabras cortadas
        text = re.sub(r"-\n", "", text)
        text = text.replace("\n", " ")

        found_products = []

        for product in product_names:

            if product in text:

                pattern = r"(\d+)\s+" + re.escape(product)
                match = re.search(pattern, text)

                if match:
                    qty = int(match.group(1))
                else:
                    qty = 1

                found_products.append(product)

                product_counts[product] += qty

        # -----------------------------
        # detectar producto principal
        # -----------------------------

        main_product = None

        for p in found_products:
            if p not in SECONDARY_PRODUCTS:
                main_product = p
                break

        pages_data.append({
            "index": i,
            "products": found_products,
            "main_product": main_product
        })


    # -----------------------------
    # Reordenar páginas
    # -----------------------------

    ordered_indexes = []
    used = set()

    # ordenar por producto principal
    for product in product_names:

        if product in SECONDARY_PRODUCTS:
            continue

        for p in pages_data:

            if p["main_product"] == product and p["index"] not in used:

                ordered_indexes.append(p["index"])
                used.add(p["index"])


    # agregar páginas restantes
    for p in pages_data:

        if p["index"] not in used:

            ordered_indexes.append(p["index"])


    # -----------------------------
    # Crear nuevo PDF
    # -----------------------------

    writer = PdfWriter()

    for idx in ordered_indexes:

        writer.add_page(reader.pages[idx])


    # -----------------------------
    # Obtener tamaño ticket
    # -----------------------------

    first_page = reader.pages[0]

    width = float(first_page.mediabox.width)
    height = float(first_page.mediabox.height)


    # -----------------------------
    # Crear resumen
    # -----------------------------

    packet = BytesIO()

    c = canvas.Canvas(packet, pagesize=(width, height))

    y = height - 40

    c.setFont("Helvetica-Bold", 10)
    c.drawString(10, y, "RESUMEN DE PRODUCTOS")

    y -= 25

    c.setFont("Helvetica", 9)

    for product, qty in product_counts.most_common():

        line = f"{qty} <- {product}"

        c.drawString(10, y, line)

        y -= 15

    c.save()

    packet.seek(0)

    summary_pdf = PdfReader(packet)

    writer.add_page(summary_pdf.pages[0])


    # -----------------------------
    # Guardar resultado
    # -----------------------------

    temp_name = "temp_" + pdf_file

    with open(temp_name, "wb") as f:
        writer.write(f)

    # reemplazar el archivo original
    os.replace(temp_name, pdf_file)

    print("PDF actualizado:", pdf_file)
