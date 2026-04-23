import requests
import io
import time
from reportlab.pdfgen import canvas

documents_to_generate = [
    {
        "filename": "Resume_John_Doe.pdf",
        "content": [
            "Applicant Name: John Doe",
            "Email: john.doe@example.com",
            "Phone: (555) 123-4567",
            "Location: Austin, TX",
            "",
            "Experience:",
            "Senior React Developer at TechCorp (2020-Present)",
            "Built dynamic dashboards using React, Vite, and Redux.",
            "",
            "Skills: React, TypeScript, GraphQL, Node.js"
        ]
    },
    {
        "filename": "Resume_Jane_Smith.pdf",
        "content": [
            "Applicant Name: Jane Smith",
            "Email: jane.smith@cybersec.io",
            "Phone: (555) 987-6543",
            "Location: New York, NY",
            "",
            "Experience:",
            "Cybersecurity Analyst at SecureBank (2018-2023)",
            "Specialized in penetration testing and network infrastructure.",
            "",
            "Education: BS Computer Science, NYU",
            "Skills: Penetration Testing, Python, Wireshark, Linux"
        ]
    },
    {
        "filename": "Resume_Deven_Patel.pdf",
        "content": [
            "Applicant Name: Deven Patel",
            "Email: deven264@test.com",
            "Location: Noida, Uttar Pradesh, India",
            "",
            "Professional Summary:",
            "Experienced AI architect and backend developer.",
            "Building scalable AI systems and offline document architectures.",
            "",
            "Skills: Python, FastAPI, SQLite, React, Machine Learning, Deepmind"
        ]
    },
    {
        "filename": "Invoice_Acme_Corp_Oct.pdf",
        "content": [
            "INVOICE",
            "Issuer: Acme Corp Supplies",
            "Bill To: Startup Inc",
            "Invoice Number: INV-8984-Acme",
            "Date Issued: October 12, 2023",
            "Due Date: November 12, 2023",
            "",
            "Items:",
            "- 10x Office Chairs",
            "- 5x Dell Monitors",
            "",
            "Total Amount: $4,500.00"
        ]
    },
    {
        "filename": "Invoice_Freelance_Design.pdf",
        "content": [
            "INVOICE - Graphic Design Services",
            "Issuer: Sarah Jones Designs",
            "Bill To: WebMakers LLC",
            "Invoice Date: Jan 5, 2024",
            "Invoice Reference: SJ-2024-001",
            "",
            "Description of work:",
            "Logo design, brand kit creation, and UI mockups.",
            "",
            "Grand Total: $1,250.00",
            "Payment Term: Net 30"
        ]
    },
    {
        "filename": "Invoice_Cloud_Hosting.pdf",
        "content": [
            "Amazon Web Services (AWS) Invoice",
            "Account: WebMakers LLC",
            "Billing Period: Feb 1 - Feb 28, 2024",
            "Invoice ID: AWS-99482911",
            "",
            "Charges:",
            "EC2 Compute: $340.50",
            "S3 Storage: $110.20",
            "CloudFront: $45.00",
            "",
            "Amount Due: $495.70"
        ]
    },
    {
        "filename": "NDA_TechCorp.pdf",
        "content": [
            "NON-DISCLOSURE AGREEMENT",
            "Effective Date: March 1, 2024",
            "",
            "Parties:",
            "1. TechCorp Inc. (Disclosing Party)",
            "2. Freelance Consulting LLC (Receiving Party)",
            "",
            "The Receiving Party agrees to maintain the strict confidentiality",
            "of all proprietary source code, business designs, and AI",
            "architectures provided by TechCorp Inc.",
            "",
            "Term: 5 Years."
        ]
    },
    {
        "filename": "Contract_Lease_Agreement.pdf",
        "content": [
            "COMMERCIAL LEASE AGREEMENT",
            "Entered into on April 15, 2023",
            "",
            "Landlord: NYC Real Estate Holdings",
            "Tenant: WebMakers LLC",
            "",
            "Premises: 123 Tech Avenue, Floor 4, New York, NY",
            "Monthly Rent: $8,000.00",
            "Security Deposit: $16,000.00",
            "",
            "Duration: 36 Months",
            "Both parties mutually agree to the terms herein specified."
        ]
    },
    {
        "filename": "Contract_Employment_Offer.pdf",
        "content": [
            "EMPLOYMENT AGREEMENT",
            "Employee Name: John Doe",
            "Employer: SecureBank",
            "Date: August 10, 2022",
            "",
            "Role: Senior Software Engineer",
            "Base Salary: $140,000 per annum",
            "Bonus Target: 10%",
            "",
            "The employee agrees to devote full time and attention to the",
            "business of SecureBank and signs a standard non-compete clause."
        ]
    },
    {
        "filename": "BankStatement_Chase_May.pdf",
        "content": [
            "CHASE BUSINESS CHECKING STATEMENT",
            "Account Name: WebMakers LLC",
            "Account Number: 8881-2292-1111",
            "Statement Period: May 1, 2024 to May 31, 2024",
            "",
            "Beginning Balance: $25,400.00",
            "Deposits: $12,000.00",
            "Withdrawals: -$8,500.00",
            "Ending Balance: $28,900.00",
            "",
            "Thank you for banking with Chase."
        ]
    },
    {
        "filename": "BankStatement_BofA_Business.pdf",
        "content": [
            "Bank of America Corporate Account",
            "Account Number: 555-444-333",
            "Entity: TechCorp Inc.",
            "Period: June 2023",
            "",
            "Opening Balance: $145,000.00",
            "Total Credits: $50,500.00",
            "Total Debits: -$62,000.00",
            "Closing Balance: $133,500.00",
            "",
            "Wire transfer fees applied: $150.00"
        ]
    },
    {
        "filename": "Receipt_Apple_Store.pdf",
        "content": [
            "APPLE STORE RECEIPT",
            "Location: 5th Avenue, NY",
            "Date: Dec 20, 2023",
            "",
            "Items:",
            "1x MacBook Pro M3 Max - $3,499.00",
            "1x AppleCare+ - $399.00",
            "",
            "Subtotal: $3,898.00",
            "Tax: $345.94",
            "Total: $4,243.94",
            "",
            "Paid via Visa ending in 4040.",
            "Thank you for your purchase!"
        ]
    }
]

def generate_pdf(lines):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.setFont("Helvetica", 12)
    y = 800
    for line in lines:
        c.drawString(50, y, line)
        y -= 20
        if y < 50:
            c.showPage()
            y = 800
    c.save()
    buffer.seek(0)
    return buffer.read()

def upload_document(filename, pdf_bytes):
    print(f"Uploading {filename}...")
    files = {'file': (filename, pdf_bytes, 'application/pdf')}
    try:
        response = requests.post("http://127.0.0.1:8000/api/upload", files=files)
        if response.status_code == 200:
            print(f"Success! {response.json().get('message')}")
        else:
            print(f"Failed. Code: {response.status_code}, Body: {response.text}")
    except Exception as e:
        print(f"Error connecting to server for {filename}: {e}")

if __name__ == "__main__":
    print("Starting automated database seed script...")
    print("Make sure Uvicorn is running on port 8000!")
    for doc in documents_to_generate:
        pdf_data = generate_pdf(doc["content"])
        upload_document(doc["filename"], pdf_data)
        # Sleep slightly to prevent slamming the small Ollama engine too hard
        time.sleep(2)
    print("Finished seeding database!")
