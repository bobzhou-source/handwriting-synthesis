# Export Formats Documentation

## Overview
The HandSynthGUI application now supports multiple export formats for your generated handwriting:

- **PNG (Transparent)** - Default format with transparency support
- **JPG (Compressed)** - Compressed format with quality control
- **PDF (Vector)** - Vector format for professional documents

## How to Use

### 1. Select Export Format
In the "Text Options" section, you'll find a new "Export Format" section with three radio buttons:
- **PNG (Transparent)**: Saves both transparent and background versions
- **JPG (Compressed)**: Saves compressed images with quality control
- **PDF (Vector)**: Saves as PDF documents

### 2. JPG Quality Control
When JPG format is selected, a quality slider appears allowing you to control the compression:
- Range: 50-100
- Default: 95 (high quality)
- Higher values = better quality, larger file size

### 3. PDF Export Requirements
For PDF export, you need to install the `reportlab` library:
```bash
pip install reportlab
```

If reportlab is not installed, the PDF option will be disabled and a note will be shown.

## File Output

### PNG Format
- `filename-alpha.png` - Transparent version
- `filename-{background}.png` - With background (white, color, or image)

### JPG Format
- `filename-{background}.jpg` - Compressed version with specified quality
- Note: JPG doesn't support transparency, so transparent backgrounds are converted to white

### PDF Format
- `filename-{background}.pdf` - Vector format suitable for printing
- Automatically scales to fit A4 page size
- Maintains high quality for professional use

## Background Compatibility

All export formats work with all background types:
- **Transparent**: PNG preserves transparency, JPG/PDF convert to white
- **White**: All formats support white backgrounds
- **Custom Color**: All formats support custom color backgrounds
- **Image**: All formats support image backgrounds

## Tips

1. **For Web Use**: Use PNG with transparent background
2. **For Email/Sharing**: Use JPG with quality 85-95
3. **For Printing**: Use PDF for best quality
4. **For Documents**: Use PDF for professional documents
5. **For Social Media**: Use JPG with quality 90-95

## Troubleshooting

### PDF Export Issues
- Ensure `reportlab` is installed: `pip install reportlab`
- Check that the PDF option is enabled (not grayed out)
- If PDF creation fails, the system will fallback to PNG

### JPG Quality Issues
- Lower quality (50-70) for smaller file sizes
- Higher quality (90-100) for better image quality
- Quality 95 is recommended for most uses

### File Size Considerations
- PNG: Largest file size, best quality, supports transparency
- JPG: Smaller file size, good quality, no transparency
- PDF: Variable size, vector format, best for printing
