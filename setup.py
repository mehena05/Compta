from setuptools import setup, find_packages

setup(
    name="ocr_pccompta",
    version="0.1.0",
    packages=find_packages(exclude=["tests*", "scripts*"]),
    python_requires=">=3.11",
    install_requires=[
        "boto3>=1.34.0",
        "openpyxl>=3.1.2",
        "opencv-python-headless>=4.9.0",
        "numpy>=1.26.0",
        "Pillow>=10.0.0",
        "python-dotenv>=1.0.0",
        "python-dateutil>=2.9.0",
    ],
    extras_require={
        "textract": ["boto3>=1.34.0"],
        "google": [
            "google-cloud-documentai>=2.20.0",
            "google-cloud-vision>=3.7.0",
        ],
        "tesseract": ["pytesseract>=0.3.10"],
        "pdf": ["pdf2image>=1.17.0"],
        "dev": [
            "pytest>=8.0.0",
            "pytest-cov>=5.0.0",
            "ruff>=0.4.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "ocr-pccompta=scripts.process_invoices:main",
        ],
    },
)
