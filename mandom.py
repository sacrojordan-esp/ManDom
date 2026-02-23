import pymupdf
import json
import os
import sys

print("=== Orden iniciada ===")

""" 1) Extraccion del diccionario de productos"""

with open("products.json", "r", encoding="utf-8") as f:
    products = json.load(f)


""" 2) Deteccion automatica de PDF"""

# Carpeta donde se encuentra el pdf

base_dir = os.path.dirname(os.path.realpath(sys.argv[0])) #Obtiene la carpeta del PDF
extensiones = (".pdf")

# Lista de PDFS

rutas_pdf = [
    os.path.join(base_dir, f) #Crea la ruta entera
    for f in os.listdir(base_dir) #Filtra los archivos pdf
    if f.lower().endswith(extensiones) #Queda como una ruta de cada pdf
]

# Apertura del PDF

if not rutas_pdf:
    print("❌ No se encontraron PDFs en la carpeta.")
else:
    for ruta in rutas_pdf:
        doc = pymupdf.open(ruta) 
    print(f"✅ {len(rutas_pdf)} PDF(s) encontrados.")


""" 3) EJECUCION DEL SCRIPT"""

for page in doc: # iterate the document pages
    text = page.get_text().lower() # get plain text

    for product in products.values(): #Localizador
        if product["name"].lower() in text:
            index = text.find(product["name"].lower()) #Position of label
            num_products = text[index-2]    
            product["count"] += int(num_products)

def create_output(name_output):
    with open(name_output, "w", encoding="utf-8") as out:
        for product in products.values():
            if product['count'] > 0:
                out.write(f"{product['count']} <- {product['name']}\n")

create_output("salida.txt")

print("\n=== Proceso finalizado ===")
input("Presiona Enter para cerrar...")