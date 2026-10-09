import os
import zipfile

def comprimir_archivos(estructura, nombre_salida="out.zip"):
    # Creamos el archivo ZIP en modo escritura con compresión
    with zipfile.ZipFile(nombre_salida, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for archivo in estructura:
            # Limpiamos posibles espacios en blanco
            archivo = archivo.strip()
            
            # Verificamos que el archivo exista localmente
            if os.path.exists(archivo):
                # arcname mantiene la ruta y estructura de carpetas dentro del zip
                zipf.write(archivo, arcname=archivo)
                print(f"[+] Agregado: {archivo}")
            else:
                print(f"[-] Omitido (no encontrado): {archivo}")

# Estructura de archivos proporcionada
estructura = [
    # Módulo de administración de mapas
    "ui/admin/mapa/EditorMapaScreen.kt",
    "ui/admin/mapa/EditorMapaViewModel.kt",
    "ui/admin/mapa/EditorMapaState.kt",
    "ui/admin/mapa/AlertaFormSheet.kt",
    
    # Componentes de mapas y visualización
    "ui/components/MapaCampus.kt",
    "map/MbtilesReader.kt",
    
    # Capa de datos y dominio
    "data/repository/AlertasRepository.kt",
    "domain/model/Alerta.kt",
]

if __name__ == "__main__":
    print("Iniciando compresión...")
    comprimir_archivos(estructura)
    print("\n¡Proceso finalizado! Archivo guardado como 'out.zip'.")