# Exporta una presentación a PDF con PowerPoint y renderiza cada diapositiva a JPG.
param([string]$Pptx, [string]$Salida, [string]$Python)
$pp = New-Object -ComObject PowerPoint.Application
try {
    $pres = $pp.Presentations.Open($Pptx, $true, $false, $false)
    $pdf = [IO.Path]::ChangeExtension($Pptx, ".pdf")
    $pres.SaveAs($pdf, 32)   # 32 = ppSaveAsPDF
    $pres.Close()
} finally { $pp.Quit() }
New-Item -ItemType Directory -Force $Salida | Out-Null
Get-ChildItem $Salida -Filter "slide-*.jpg" | Remove-Item
$codigo = "import fitz, sys`nd = fitz.open(sys.argv[1])`nfor i, p in enumerate(d, 1):`n    p.get_pixmap(matrix=fitz.Matrix(1.6, 1.6)).save(f'{sys.argv[2]}/slide-{i:02d}.jpg')`nprint(len(d), 'diapositivas')"
& $Python -W ignore -c $codigo $pdf $Salida
