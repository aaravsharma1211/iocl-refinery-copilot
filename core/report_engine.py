import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


class ReportEngine:
    """Generates formal, downloadable PDF compliance reports from Copilot answers."""
    
    @staticmethod
    def generate_pdf_report(title: str, summary: str, citations: list[dict]) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=letter, 
            rightMargin=36, 
            leftMargin=36, 
            topMargin=36, 
            bottomMargin=36
        )
        story = []
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor='#1f4e79',
            spaceAfter=12
        )
        body_style = ParagraphStyle(
            'ReportBody',
            parent=styles['Normal'],
            fontSize=11,
            leading=16,
            spaceAfter=8
        )
        
        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 10))
        story.append(Paragraph("<b>Executive Summary & Safety Analysis:</b>", body_style))
        story.append(Paragraph(summary, body_style))
        story.append(Spacer(1, 15))
        
        if citations:
            story.append(Paragraph("<b>Reference Citations & Source Versions:</b>", body_style))
            for cit in citations:
                cit_text = (
                    f"• <b>{cit.get('filename')}</b> "
                    f"(Page {cit.get('page')}, Ver: {cit.get('version', 'v1.0')}): "
                    f"{cit.get('snippet')}"
                )
                story.append(Paragraph(cit_text, body_style))
                
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()