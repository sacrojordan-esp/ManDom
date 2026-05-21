#!/usr/bin/env python3
"""
Módulo para procesar PDFs de notas de venta.
Extrae productos, agrupa por producto en común, y genera un PDF con resumen.
"""
import re
import fitz  # pymupdf
from collections import defaultdict
from typing import List, Dict, Tuple


# ============================================================================
# MÓDULO: LECTOR - Extrae información de cada página del PDF
# ============================================================================

class PDFReader:
    """Lee y extrae datos de cada página del PDF de notas de venta."""

    @staticmethod
    def extract_products_from_page(page_text: str) -> List[str]:
        """Extrae la lista de productos del texto de una página.
        Funciona con dos formatos:
        - Con bullets: "• 1 PRODUCTO REGALO MUJER"
        - Sin bullets: "1 MASAJEADOR SMART DE RODILLA"
        """
        productos = []
        lines = page_text.split('\n')
        in_productos = False

        # Keywords que marcan el fin de la sección de productos
        fin_keywords = ['NOTA:', 'F. ENT', 'F. DESP', 'TOTAL', 'CLIENTE', 'VENDEDOR', 'DNI/RUC', 'Distrito:', 'Tel:']

        for i, line in enumerate(lines):
            line = line.strip()

            # Detectar inicio de la sección de productos
            if 'PRODUCTOS' in line.upper():
                in_productos = True
                continue

            if in_productos:
                # Si es línea vacía o es un keyword de fin, salir
                if not line:
                    continue
                if any(kw in line.upper() for kw in fin_keywords):
                    in_productos = False
                    continue

                # Formato 1: con bullet "• 1 PRODUCTO..." -> quitar bullet y mantener número
                # Formato 2: número al inicio "1 PRODUCTO..."
                producto = line
                if producto.startswith('•'):
                    producto = producto[1:].strip()  # Quitar bullet

                # Ahora la línea debe empezar con número + espacio
                if re.match(r'^\d+\s+', producto):
                    # Unir con línea siguiente si es continuación (ej: "CARGO LEGGINS -" + "TALLA XL")
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if next_line and not re.match(r'^\d+\s+', next_line) and not next_line.startswith('•'):
                            # Verificar que no sea un keyword
                            if not any(kw in next_line.upper() for kw in fin_keywords):
                                producto = producto + ' ' + next_line

                    if producto:
                        productos.append(producto)

        return productos

    @staticmethod
    def extract_all_pages(pdf_path: str) -> List[Dict]:
        """
        Lee todas las páginas del PDF y extrae la información de cada una.
        Returns: List[Dict] con datos de cada página
        """
        doc = fitz.open(pdf_path)
        paginas = []

        for page_num, page in enumerate(doc):
            text = page.get_text()

            # Extraer número de ticket (guía)
            guia_match = re.search(r'Guía:\s*([A-Z0-9]+)', text)
            guia = guia_match.group(1) if guia_match else f"PAG_{page_num + 1}"

            # Extraer número de nota (NVD)
            nvd_match = re.search(r'#(NVD\d+)', text)
            nvd = nvd_match.group(1) if nvd_match else f"ND_{page_num + 1}"

            # Extraer cliente
            cliente_match = re.search(r'#\w+\s*\|\s*([^\n]+)', text)
            cliente = cliente_match.group(1).strip() if cliente_match else "Desconocido"

            # Extraer productos
            productos = PDFReader.extract_products_from_page(text)

            paginas.append({
                'page_num': page_num,
                'guia': guia,
                'nvd': nvd,
                'cliente': cliente,
                'productos': productos,
                'raw_text': text
            })

        doc.close()
        return paginas


# ============================================================================
# MÓDULO: PROCESADOR - Cuenta, filtra y agrupa productos
# ============================================================================

class ProductProcessor:
    """Procesa los productos extraídos: filtra, cuenta y agrupa."""

    # Palabras que indican producto de regalo
    REGALO_PATTERNS = [
        r'REGALO',
        r'PROMOCI[ÓO]N',
        r'BONIFICACI[ÓO]N',
        r'OBSEQUIO'
    ]

    @staticmethod
    def is_regalo(producto: str) -> bool:
        """Determina si un producto es un regalo."""
        upper_producto = producto.upper()
        return any(re.search(pattern, upper_producto) for pattern in ProductProcessor.REGALO_PATTERNS)

    @staticmethod
    def normalize_product_name(producto: str) -> str:
        """
        Normaliza el nombre del producto para comparación.
        - Limpia saltos de línea
        - Elimina palabras de regalo
        - Elimina " - NOWO" del final
        - Elimina el número/cantidad al inicio
        - Convierte a minúsculas
        """
        # Limpiar saltos de línea
        producto = producto.replace('\n', ' ').replace('\r', ' ')

        # Quitar indicadores de regalo
        for pattern in ProductProcessor.REGALO_PATTERNS:
            producto = re.sub(pattern, '', producto, flags=re.IGNORECASE)

        # Quitar " - NOWO" del final
        producto = re.sub(r'\s*-\s*NOWO$', '', producto, flags=re.IGNORECASE)

        # Quitar cantidad al inicio (ej: "1 ADAPTADOR" -> "adaptador")
        producto = re.sub(r'^\d+\s+', '', producto.strip())

        # Limpiar espacios extra y convertir a minúsculas
        producto = ' '.join(producto.split()).lower().strip()

        return producto if producto else "otro"

    @staticmethod
    def calculate_similarity(name1: str, name2: str) -> float:
        """Calcula similitud entre dos nombres de productos."""
        return SequenceMatcher(None, name1, name2).ratio()

    @staticmethod
    def group_by_common_product(paginas: List[Dict]) -> List[Tuple[str, List[Dict]]]:
        """
        Agrupa las páginas por producto NO-regalo en COMÚN.
        Si dos páginas comparten al menos un producto no-regalo, van al mismo grupo.

        Returns: Lista de (producto_key, lista_paginas) ordenadas por cantidad
        """
        # Obtener productos no-regalo de cada página
        productos_por_pagina = []
        for pagina in paginas:
            productos_no_regalo = [p for p in pagina['productos'] if not ProductProcessor.is_regalo(p)]
            # Normalizar los nombres para comparación
            productos_normalizados = [ProductProcessor.normalize_product_name(p) for p in productos_no_regalo]

            productos_por_pagina.append({
                'pagina': pagina,
                'productos_no_regalo': productos_no_regalo,
                'productos_normalizados': productos_normalizados,
                'has_producto': bool(productos_normalizados)  # Tiene producto no-regalo?
            })

        # Primera pasada: encontrar TODOS los productos únicos
        productos_unicos = set()
        for item in productos_por_pagina:
            for prod_norm in item['productos_normalizados']:
                productos_unicos.add(prod_norm)

        # Segunda pasada: para cada producto único, crear un grupo con TODAS las páginas que lo contienen
        grupos_dict = {}  # producto -> lista de páginas

        for prod in productos_unicos:
            paginas_con_producto = []
            for item in productos_por_pagina:
                if prod in item['productos_normalizados']:
                    paginas_con_producto.append(item)

            if paginas_con_producto:
                grupos_dict[prod] = paginas_con_producto

        # Tercera pasada: UNIFICAR grupos que tienen páginas en común
        # Si el grupo A y el grupo B comparten al menos una página, fusionar
        unificado = True
        while unificado:
            unificado = False
            productos_a_fusionar = []

            productos_list = list(grupos_dict.keys())
            for i in range(len(productos_list)):
                for j in range(i + 1, len(productos_list)):
                    prod_a = productos_list[i]
                    prod_b = productos_list[j]

                    # Ver si comparten páginas
                    paginas_a = set(id(item) for item in grupos_dict[prod_a])
                    paginas_b = set(id(item) for item in grupos_dict[prod_b])

                    if paginas_a & paginas_b:  # Hay intersección
                        # Fusionar
                        productos_a_fusionar.append((prod_a, prod_b))
                        unificado = True
                        break
                if unificado:
                    break

            # Ejecutar fusiones
            for prod_a, prod_b in productos_a_fusionar:
                # Combinar grupos
                combinado =grupos_dict[prod_a] + [item for item in grupos_dict[prod_b] if item not in grupos_dict[prod_a]]
                # Usar el producto más largo como clave
                clave_nueva = prod_a if len(prod_a) >= len(prod_b) else prod_b
                grupos_dict[clave_nueva] = combinado
                del grupos_dict[prod_b]

        # Convertir a lista de tuplas y ordenar
        grupos = []
        for clave, items in grupos_dict.items():
            grupos.append((clave, items))

        # Ordenar por número de páginas (mayor cantidad primero)
        grupos.sort(key=lambda x: len(x[1]), reverse=True)

        # RECALCULAR la clave (líder) basándose en el producto más común del grupo
        grupos_final = []
        for clave, items in grupos:
            # Contar cuántas páginas tienen cada producto
            conteo_productos = {}
            for item in items:
                for prod in item['productos_normalizados']:
                    conteo_productos[prod] = conteo_productos.get(prod, 0) + 1

            # El líder es el producto con más páginas en este grupo
            if conteo_productos:
                lider = max(conteo_productos.items(), key=lambda x: x[1])[0]
            else:
                lider = "sin_producto"

            grupos_final.append((lider, items))

        # Re-ordenar por cantidad de páginas
        grupos_final.sort(key=lambda x: len(x[1]), reverse=True)

        return grupos_final

    @staticmethod
    def group_similar_products(paginas: List[Dict], similarity_threshold: float = 0.7) -> List[Tuple[str, List[Dict]]]:
        """
        Agrupa las páginas por productos similares.
        Ignora los productos de regalo para la agrupación.
        Usa TODOS los productos no-regalo para hacer la clave (no solo el primero).
        Returns: Lista de (producto_key, lista_paginas) ordenadas por cantidad
        """
        # Obtener productos no-regalo de cada página
        productos_por_pagina = []
        for pagina in paginas:
            productos_no_regalo = [p for p in pagina['productos'] if not ProductProcessor.is_regalo(p)]
            if productos_no_regalo:
                # Usar TODOS los productos no-regalo como clave (ordenados)
                clave = " | ".join(sorted([ProductProcessor.normalize_product_name(p) for p in productos_no_regalo]))
            else:
                clave = "sin_producto"

            productos_por_pagina.append({
                'pagina': pagina,
                'clave': clave,
                'productos_no_regalo': productos_no_regalo
            })

        # Agrupar por similitud
        grupos = []
        asignadas = set()

        for i, item in enumerate(productos_por_pagina):
            if i in asignadas:
                continue

            # Crear nuevo grupo
            grupo = [item]
            asignadas.add(i)

            # Buscar similares
            for j in range(i + 1, len(productos_por_pagina)):
                if j in asignadas:
                    continue

                similarity = ProductProcessor.calculate_similarity(
                    item['clave'],
                    productos_por_pagina[j]['clave']
                )

                if similarity >= similarity_threshold:
                    grupo.append(productos_por_pagina[j])
                    asignadas.add(j)

            grupos.append((item['clave'], grupo))

        # Ordenar por número de páginas (mayor cantidad primero)
        grupos.sort(key=lambda x: len(x[1]), reverse=True)

        return grupos

    @staticmethod
    def count_products(paginas: List[Dict]) -> Dict[str, int]:
        """
        Cuenta todos los productos (incluyendo regalos).
        Respeta la cantidad que dice en cada línea (ej: "2 CERA ANTI-FRIZZ" = 2)
        Returns: Dict con nombre_producto -> cantidad
        """
        contador = defaultdict(int)

        for pagina in paginas:
            for producto in pagina['productos']:
                # Limpiar saltos de línea dentro del producto (ej: "CARGO LEGGINS -\nTALLA M" -> "CARGO LEGGINS - TALLA M")
                producto = producto.replace('\n', ' ')
                producto = producto.replace('\r', ' ')

                # Extraer cantidad al inicio (ej: "2 CERA ANTI-FRIZZ" -> cantidad=2, nombre="CERA ANTI-FRIZZ")
                match = re.match(r'^(\d+)\s+(.+)$', producto.strip())
                if match:
                    cantidad = int(match.group(1))
                    nombre = match.group(2).strip()
                else:
                    cantidad = 1
                    nombre = producto.strip()

                contador[nombre] += cantidad

        return dict(contador)

    @staticmethod
    def generate_summary(paginas: List[Dict]) -> str:
        """Genera el texto de resumen con todos los productos contados."""
        conteo = ProductProcessor.count_products(paginas)

        lineas = []

        for producto, cantidad in sorted(conteo.items()):
            # Quitar " - NOWO" del final para el resumen
            producto_limpio = re.sub(r'\s*-\s*NOWO$', '', producto, flags=re.IGNORECASE).strip()
            # Formato: CANTIDAD PRODUCTO (cantidad a la izquierda)
            lineas.append(f"{cantidad} {producto_limpio}")

        return "\n".join(lineas)


# ============================================================================
# MÓDULO: ESCRITOR - Crea el PDF de salida
# ============================================================================

class PDFWriter:
    """Escribe el PDF de salida con páginas reordenadas y resumen."""

    # Tamaño del ticket original (226.77 x 226.77 puntos)
    TICKET_SIZE = (226.77, 226.77)

    @staticmethod
    def truncate_long_product_name(producto: str, max_len: int = 35) -> str:
        """
        Trunca productos muy largos eliminando caracteres del medio.
        Ejemplo: "CARGO LEGGINS MOLDEADOR PIERNA ANCHA - TALLA M" (41 chars)
                 -> "CARGO LEGGINS ANCHA - TALLA M" (29 chars)

        Mantiene el inicio y el final, elimina caracteres del medio.
        """
        if len(producto) <= max_len:
            return producto

        # Mantener inicio y final, truncar medio
        inicio_len = max_len // 2
        final_len = max_len - inicio_len - 3  # 3 para "..."

        return producto[:inicio_len] + "..." + producto[-final_len:]

    @staticmethod
    def create_output_pdf(input_path: str, output_path: str, paginas: List[Dict], grupos: List[Tuple[str, List[Dict]]]) -> None:
        """
        Crea el PDF de salida:
        1. Páginas reordenadas por similitud de productos
        2. Página de resumen al final
        """
        doc_input = fitz.open(input_path)

        # Crear nuevo documento
        doc_output = fitz.open()

        # Agregar páginas reordenadas según grupos
        for clave, grupo in grupos:
            for item in grupo:
                page_num = item['pagina']['page_num']
                doc_output.insert_pdf(doc_input, from_page=page_num, to_page=page_num)

        # Agregar páginas que no entraron en grupos (sin producto no-regalo)
        paginas_en_grupos = set()
        for _, grupo in grupos:
            for item in grupo:
                paginas_en_grupos.add(item['pagina']['page_num'])

        for pagina in paginas:
            if pagina['page_num'] not in paginas_en_grupos:
                doc_output.insert_pdf(doc_input, from_page=pagina['page_num'], to_page=pagina['page_num'])

        # Crear página de resumen con el mismo tamaño
        resumen = ProductProcessor.generate_summary(paginas)

        lines = resumen.split('\n')
        page_width = PDFWriter.TICKET_SIZE[0]
        page_height = PDFWriter.TICKET_SIZE[1]
        margin_top = 20
        margin_bottom = 10
        fontsize = 8
        line_height = 10

        y_pos = margin_top
        current_page = None

        for line in lines:
            if not line.strip():
                continue

            # Formatear línea (truncar si muy larga)
            if len(line) > 40:
                parts = line.split(' ', 1)
                if len(parts) == 2:
                    cant = parts[0]
                    nombre = parts[1]
                    nombre_truncado = PDFWriter.truncate_long_product_name(nombre, max_len=35)
                    line_final = f"{cant} {nombre_truncado}"
                else:
                    line_final = line[:35] + "..."
            else:
                line_final = line

            # Crear nueva página si es necesario
            if current_page is None or y_pos + line_height > page_height - margin_bottom:
                current_page = doc_output.new_page(width=page_width, height=page_height)
                y_pos = margin_top

            # Escribir la línea
            current_page.insert_text((5, y_pos), line_final, fontsize=fontsize)
            y_pos += line_height

        # Guardar documento
        doc_output.save(output_path)
        doc_input.close()
        doc_output.close()


# ============================================================================
# MÓDULO PRINCIPAL - Orquestador
# ============================================================================

def process_pdf(input_path: str, output_path: str = None, modo_agrupacion: str = "comun") -> Dict:
    """
    Procesa el PDF de notas de venta.

    Args:
        input_path: Ruta al PDF de entrada
        output_path: Ruta al PDF de salida (opcional, usa nombre automático)
        modo_agrupacion: "comun" (por producto en común) o "similar" (por similitud)

    Returns:
        Dict con información del procesamiento
    """
    if output_path is None:
        output_path = input_path.replace('.pdf', '_creado.pdf')

    # 1. Leer el PDF
    print(f"Leyendo PDF: {input_path}")
    paginas = PDFReader.extract_all_pages(input_path)
    print(f"  - Extraídas {len(paginas)} páginas")

    # 2. Contar productos
    conteo = ProductProcessor.count_products(paginas)
    total = sum(conteo.values())
    print(f"\nProductos encontrados: {total}")
    for prod, cant in conteo.items():
        print(f"  - {prod}: {cant}")

    # 3. Agrupar productos
    if modo_agrupacion == "comun":
        print("\nAgrupando productos por producto en COMÚN...")
        grupos = ProductProcessor.group_by_common_product(paginas)
    else:
        print("\nAgrupando productos por SIMILITUD...")
        grupos = ProductProcessor.group_similar_products(paginas)

    print(f"  - {len(grupos)} grupos formados")

    for clave, grupo in grupos:
        # Mostrar los productos no-regalo del grupo
        productos_mostrar = []
        for item in grupo[:3]:  # Mostrar hasta 3 ejemplos
            prods = item.get('productos_no_regalo', item.get('pagina', {}).get('productos', []))
            if prods:
                productos_mostrar.append(prods[0][:30])
        print(f"    * '{clave[:40]}...': {len(grupo)} página(s)")

    # 4. Generar PDF de salida
    print(f"\nGenerando PDF de salida: {output_path}")
    PDFWriter.create_output_pdf(input_path, output_path, paginas, grupos)

    return {
        'input': input_path,
        'output': output_path,
        'total_pages': len(paginas),
        'total_products': total,
        'conteo': conteo,
        'grupos': [(clave, len(grp)) for clave, grp in grupos]
    }


# ============================================================================
# ENTRADA PRINCIPAL
# ============================================================================

if __name__ == "__main__":
    import sys
    import os

    # Determinar directorio de trabajo
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Si se pasa argumento, usar ese archivo
    if len(sys.argv) > 1:
        input_pdf = sys.argv[1]
        output_pdf = sys.argv[2] if len(sys.argv) > 2 else input_pdf.replace('.pdf', '_creado.pdf')
        modo = sys.argv[3] if len(sys.argv) > 3 else "comun"
        resultado = process_pdf(input_pdf, output_pdf, modo)
        print(f"\n✅ Proceso completado: {resultado['output']}")
    else:
        # Buscar todos los PDFs en el directorio actual (recursivamente)
        pdfs = []
        for root, dirs, files in os.walk(script_dir):
            for f in files:
                # Solo procesar PDFs que no terminan en _creado.pdf
                if f.endswith('.pdf') and not f.endswith('_creado.pdf'):
                    pdfs.append(os.path.join(root, f))

        if not pdfs:
            print("No se encontraron PDFs en el directorio.")
        else:
            print(f"Se encontraron {len(pdfs)} PDF(s) para procesar.\n")
            for input_pdf in pdfs:
                # Output en el mismo directorio que el input
                base = input_pdf[:-4]  #.quita .pdf
                output_pdf = base + "_creado.pdf"
                filename = os.path.basename(input_pdf)
                print(f"Procesando: {filename}")
                resultado = process_pdf(input_pdf, output_pdf, modo_agrupacion="comun")
                print(f"✅ Completado: {resultado['output']}\n")
