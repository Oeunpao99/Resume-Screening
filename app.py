# app.py - ENHANCED JSON STRUCTURE VERSION (Render Compatible)
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import tempfile
import re
import json
from datetime import datetime
import traceback

app = FastAPI(
    title="Enhanced Resume Analyzer API",
    description="API for analyzing resumes and extracting structured candidate information",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ResumeAnalysisResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF using pdfminer"""
    try:
        from pdfminer.high_level import extract_text
        text = extract_text(file_path)
        return text
    except Exception as e:
        print(f"PDF text extraction error: {e}")
        return ""

def parse_resume_with_pyresparser(file_path: str) -> Dict[str, Any]:
    """Parse resume using PyResParser with error handling"""
    try:
        from pyresparser import ResumeParser
        data = ResumeParser(file_path).get_extracted_data()
        return data if data else {}
    except Exception as e:
        print(f"PyResParser error: {e}")
        # Return basic structure as fallback
        return {
            'skills': [],
            'name': '',
            'email': '',
            'mobile_number': '',
            'no_of_pages': 1
        }

def extract_personal_info(text: str) -> Dict[str, str]:
    """Extract comprehensive personal information"""
    info = {
        "full_name": "",
        "location": "",
        "first_name": "",
        "last_name": "",
        "email": "",
        "phone": "",
        "address": "",
        "linkedin": "",
        "github": "",
        "portfolio": ""
    }
    
    lines = text.split('\n')
    
    # Extract name (usually first meaningful line)
    for i, line in enumerate(lines[:10]):
        line_clean = line.strip()
        if (len(line_clean) > 2 and len(line_clean) < 50 and
            not any(word in line_clean.lower() for word in ['resume', 'cv', 'curriculum', 'vitae', 'phone', 'email', 'linkedin']) and
            re.match(r'^[A-Za-z\s\.\-]+$', line_clean)):
            info["full_name"] = line_clean
            name_parts = line_clean.split()
            if name_parts:
                info["first_name"] = name_parts[0]
                info["last_name"] = name_parts[-1] if len(name_parts) > 1 else ""
            break
    
    # Extract email
    email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
    if email_match:
        info["email"] = email_match.group() 
    
    # Extract phone
    phone_patterns = [
        r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
        r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b'
    ]
    for pattern in phone_patterns:
        phone_match = re.search(pattern, text)
        if phone_match:
            info["phone"] = phone_match.group()
            break
    
    # Extract LinkedIn
    linkedin_match = re.search(r'linkedin\.com/in/[^\s]+', text)
    if linkedin_match:
        info["linkedin"] = linkedin_match.group()
    
    # Extract GitHub
    github_match = re.search(r'github\.com/[^\s]+', text)
    if github_match:
        info["github"] = github_match.group()
    
    # Extract portfolio
    portfolio_match = re.search(r'((https?://|www\.)[\w\-\.\~:/?#@!$&\'"\(\)\*\+,;=%]+)', text)
    if portfolio_match:
        candidate = portfolio_match.group(1).strip()
        if '@' not in candidate and 'linkedin' not in candidate and 'github' not in candidate:
            info["portfolio"] = candidate

    # Extract location/address
    address_tokens = ['address', 'location', 'city', 'province', 'district', 'street', 'road']
    for line in lines[:12]:
        low = line.strip().lower()
        if any(tok in low for tok in address_tokens) and len(line.strip()) > 5:
            info["location"] = line.strip()
            info["address"] = line.strip()
            break

    if not info["location"]:
        for line in lines[:8]:
            if ',' in line and len(line.strip()) > 8 and not re.search(r'@', line):
                info["location"] = line.strip()
                info["address"] = line.strip()
                break

    return info

def extract_summary(text: str) -> str:
    """Extract professional summary/objective"""
    summary = ""
    lines = text.split('\n')
    in_summary = False
    
    for line in lines:
        line_clean = line.strip()
        if any(keyword in line_clean.lower() for keyword in ['summary', 'objective', 'profile', 'about']):
            in_summary = True
            continue
        elif in_summary:
            if line_clean and len(line_clean) > 10:
                if any(section in line_clean.lower() for section in ['experience', 'education', 'skills', 'projects']):
                    break
                summary += line_clean + " "
            else:
                if summary:
                    break
    
    return summary.strip()

def extract_work_experience(text: str) -> List[Dict[str, Any]]:
    """Extract work experience with detailed information"""
    experience = []
    lines = text.split('\n')
    current_job = {}
    in_experience_section = False
    
    for i, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean:
            continue
        
        if any(keyword in line_clean.lower() for keyword in ['experience', 'work experience', 'employment', 'work history']):
            in_experience_section = True
            continue
            
        if in_experience_section:
            if any(section in line_clean.lower() for section in ['education', 'skills', 'projects', 'certifications']):
                break
            
            if not current_job and len(line_clean) > 5:
                # Try to extract company and position
                if re.search(r'\bat\b', line_clean, re.IGNORECASE):
                    parts_at = re.split(r'\bat\b', line_clean, flags=re.IGNORECASE)
                    if len(parts_at) >= 2:
                        title_part = parts_at[0].strip()
                        company_part = parts_at[1].strip()
                        current_job = {
                            "company_name": company_part,
                            "job_title": title_part,
                            "start_date": "",
                            "end_date": "",
                            "duration": "",
                            "responsibilities": []
                        }
                else:
                    # Try other separators
                    parts = re.split(r'[|\-•,\u2013\u2014]', line_clean)
                    if len(parts) >= 2:
                        company_guess = parts[0].strip()
                        title_guess = parts[1].strip()
                        current_job = {
                            "company_name": company_guess,
                            "job_title": title_guess,
                            "start_date": "",
                            "end_date": "",
                            "duration": "",
                            "responsibilities": []
                        }

                # Extract dates
                date_match = re.search(r'(\w+\s*\d{4}\s*[-–]\s*\w+\s*\d{4}|\d{4}\s*[-–]\s*\d{4}|\d{4}\s*[-–]\s*Present|Present|Current)', line_clean)
                if date_match and current_job:
                    date_str = date_match.group()
                    dates = re.findall(r'(19|20)\d{2}|Present|Current', date_str)
                    if len(dates) >= 1:
                        current_job["start_date"] = dates[0] + "-01" if dates[0] not in ['Present', 'Current'] else ""
                    if len(dates) >= 2:
                        current_job["end_date"] = dates[1] + "-01" if dates[1] not in ['Present', 'Current'] else "Present"
                    current_job["duration"] = date_str
            
            elif current_job:
                # Collect responsibilities
                if (line_clean.startswith('•') or line_clean.startswith('-') or 
                    (len(line_clean) > 20 and not re.search(r'(19|20)\d{2}', line_clean))):
                    responsibility = re.sub(r'^[•\-]\s*', '', line_clean)
                    if len(responsibility) > 10:
                        current_job["responsibilities"].append(responsibility)

                # Save job if we hit next section
                if (i + 1 < len(lines) and 
                    any(section in lines[i + 1].lower() for section in ['education', 'skills'])):
                    experience.append(current_job)
                    current_job = {}
    
    if current_job:
        experience.append(current_job)
    
    return experience

def extract_education(text: str) -> List[Dict[str, str]]:
    """Extract education information"""
    education = []
    lines = text.split('\n')
    
    current_edu = {}
    in_education_section = False
    
    for i, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean:
            continue
            
        if any(keyword in line_clean.lower() for keyword in ['education', 'academic', 'qualifications']):
            in_education_section = True
            continue
            
        if in_education_section:
            if any(section in line_clean.lower() for section in ['experience', 'skills', 'projects', 'certifications']):
                break

            if not current_edu and len(line_clean) > 5:
                if any(degree in line_clean.lower() for degree in ['bachelor', 'master', 'phd', 'associate', 'diploma', 'degree']):
                    current_edu = {
                        "degree": "",
                        "major": "",
                        "school_name": "",
                        "start_date": "",
                        "end_date": "",
                        "gpa": ""
                    }
                    
                    # Extract institution
                    if 'university' in line_clean.lower() or 'college' in line_clean.lower():
                        current_edu["school_name"] = line_clean
                    else:
                        current_edu["degree"] = line_clean
                    
                    # Extract year
                    year_match = re.search(r'(19|20)\d{2}', line_clean)
                    if year_match:
                        current_edu["end_date"] = year_match.group() + "-01"
                    
                    # Extract GPA
                    gpa_match = re.search(r'GPA\s*:?\s*(\d\.\d{1,2})', line_clean, re.IGNORECASE)
                    if gpa_match:
                        current_edu["gpa"] = gpa_match.group(1)
            
            elif current_edu:
                if not current_edu["school_name"] and ('university' in line_clean.lower() or 'college' in line_clean.lower()):
                    current_edu["school_name"] = line_clean
                
                # Save education entry
                if (i + 1 < len(lines) and 
                    any(section in lines[i + 1].lower() for section in ['experience', 'skills', 'projects'])):
                    education.append(current_edu)
                    current_edu = {}
    
    if current_edu:
        education.append(current_edu)
    
    return education

def extract_skills(text: str) -> Dict[str, List[str]]:
    """Extract and categorize skills"""
    skills = {
        "programming": [],
        "web": [],
        "data": [],
        "devops": [],
        "tools": [],
        "soft_skills": []
    }
    
    skill_categories = {
        "programming": [
            'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'php', 'ruby'
        ],
        "web": [
            'html', 'css', 'react', 'angular', 'vue', 'node.js', 'express', 'django', 
            'flask', 'spring', 'laravel'
        ],
        "data": [
            'sql', 'mysql', 'postgresql', 'mongodb', 'redis',
            'pandas', 'numpy', 'data analysis', 'machine learning'
        ],
        "devops": [
            'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'jenkins', 'gitlab',
            'terraform', 'linux'
        ],
        "tools": [
            'git', 'github', 'gitlab', 'jira', 'docker', 'postman'
        ],
        "soft_skills": [
            'leadership', 'communication', 'teamwork', 'problem solving', 'critical thinking',
            'project management', 'agile', 'scrum'
        ]
    }
    
    text_lower = text.lower()
    
    for category, keywords in skill_categories.items():
        for keyword in keywords:
            if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
                normalized_name = keyword.title()
                skills[category].append(normalized_name)
    
    # Remove duplicates
    for category in skills:
        skills[category] = list(set(skills[category]))
    
    return skills

def extract_projects(text: str) -> List[Dict[str, Any]]:
    """Extract project information"""
    projects = []
    lines = text.split('\n')
    
    current_project = {}
    in_project_section = False
    
    for i, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean:
            continue
            
        # Detect projects section
        if any(keyword in line_clean.lower() for keyword in ['projects', 'personal projects', 'portfolio']):
            in_project_section = True
            continue
            
        if in_project_section:
            # Check if we're entering a new section
            if any(section in line_clean.lower() for section in ['experience', 'education', 'skills', 'certifications']):
                break
        
            if not current_project and len(line_clean) > 5 and len(line_clean) < 100:
                current_project = {
                    "title": line_clean,
                    "description": "",
                    "technologies": [],
                    "role": "",
                    "duration": ""
                }
            
            elif current_project:
                # Collect description and technologies
                if len(line_clean) > 20:
                    if not current_project["description"]:
                        current_project["description"] = line_clean
                    else:
                        # Extract technologies from description
                        tech_keywords = ['python', 'java', 'react', 'node', 'sql', 'mongodb', 'aws']
                        found_tech = [tech for tech in tech_keywords if tech in line_clean.lower()]
                        current_project["technologies"].extend(found_tech)
                
                # Save project
                if (i + 1 < len(lines) and 
                    (len(lines[i + 1].strip()) == 0 or 
                     any(section in lines[i + 1].lower() for section in ['experience', 'education']))):
                    projects.append(current_project)
                    current_project = {}
    
    if current_project:
        projects.append(current_project)
    
    return projects

def extract_additional_info(text: str) -> Dict[str, Any]:
    """Extract certifications, languages, awards"""
    info = {
        "certifications": [],
        "languages": [],
        "awards": []
    }
    
    lines = text.split('\n')
    current_section = ""
    
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
            
        # Detect sections
        low = line_clean.lower()
        if low.startswith('certificat') or low.startswith('certification'):
            current_section = "certifications"
            continue
        elif low.startswith('language') or low == 'languages' or low.startswith('languages:'):
            current_section = "languages"
            continue
        elif low.startswith('award') or low.startswith('awards') or 'honor' in low:
            current_section = "awards"
            continue
            
        # Add items to current section
        if current_section and len(line_clean) > 2:
            if current_section == "certifications":
                info["certifications"].append(line_clean)
            elif current_section == "languages":
                info["languages"].append(line_clean)
            elif current_section == "awards":
                info["awards"].append(line_clean)
    
    return info

def calculate_experience_level(work_experience: List[Dict], text: str) -> str:
    """Determine candidate experience level"""
    total_years = 0

    for job in work_experience:
        if job.get("start_date") and job.get("end_date"):
            try:
                start_year = int(job["start_date"][:4]) if job["start_date"] else 0
                end_year = int(job["end_date"][:4]) if job["end_date"] != "Present" else datetime.now().year
                total_years += (end_year - start_year)
            except:
                pass

    if total_years == 0:
        if len(text) > 3000:
            total_years = 3
        elif len(text) > 1500:
            total_years = 1
        else:
            total_years = 0
    
    if total_years >= 5:
        return "Experienced"
    elif total_years >= 2:
        return "Intermediate"
    else:
        return "Fresher"

def calculate_total_experience(work_experience: List[Dict]) -> str:
    """Calculate total experience in years"""
    total_months = 0
    
    for job in work_experience:
        if job.get("start_date") and job.get("end_date"):
            try:
                start_date = job["start_date"]
                end_date = job["end_date"]
                
                if end_date == "Present":
                    end_date = datetime.now().strftime("%Y-%m")
                
                start_year, start_month = map(int, start_date.split('-'))
                end_year, end_month = map(int, end_date.split('-'))
                
                total_months += (end_year - start_year) * 12 + (end_month - start_month)
            except:
                continue
    
    years = total_months // 12
    months = total_months % 12
    
    if years == 0:
        return f"{months} months"
    elif months == 0:
        return f"{years} years"
    else:
        return f"{years} years {months} months"

@app.post("/analyze-resume", response_model=ResumeAnalysisResponse)
async def analyze_resume(file: UploadFile = File(...)):
    """
    Analyze uploaded resume and return structured JSON data
    """
    temp_path = None
    try:
        print(f"🔍 Starting comprehensive analysis for: {file.filename}")
        
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        # Save uploaded file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = temp_file.name
        
        # Extract text from PDF
        print("📄 Extracting text from PDF...")
        resume_text = extract_text_from_pdf(temp_path)
        
        if not resume_text or len(resume_text.strip()) < 50:
            raise HTTPException(status_code=400, detail="Could not extract meaningful text from PDF")
        
        print(f"📝 Extracted {len(resume_text)} characters")
        
        # Extract all structured information
        print("🔧 Extracting structured information...")
        
        # Get basic data from pyresparser
        basic_data = parse_resume_with_pyresparser(temp_path)
        
        personal_info = extract_personal_info(resume_text)
        summary = extract_summary(resume_text)
        work_experience = extract_work_experience(resume_text)
        education = extract_education(resume_text)
        skills = extract_skills(resume_text)
        projects = extract_projects(resume_text)
        additional_info = extract_additional_info(resume_text)

        # Calculate experience metrics
        experience_level = calculate_experience_level(work_experience, resume_text)
        total_experience = calculate_total_experience(work_experience)
        
        # Build comprehensive JSON response
        structured_data = {
            "personal_info": personal_info,
            "summary": summary,
            "work_experience": work_experience,
            "education": education,
            "skills": skills,
            "projects": projects,
            "certifications": additional_info["certifications"],
            "languages": additional_info["languages"],
            "awards": additional_info["awards"],
            "total_experience": total_experience,
            "experience_level": experience_level,
            "additional_info": f"Analyzed on {datetime.now().strftime('%Y-%m-%d')}. Text length: {len(resume_text)} characters."
        }
        
        print("✅ Comprehensive analysis completed successfully")
        return ResumeAnalysisResponse(
            success=True,
            message="Resume analyzed successfully with structured data extraction",
            data=structured_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"💥 Unexpected error: {e}")
        print(f"🔍 Stack trace: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, 
            detail=f"Analysis failed: {str(e)}"
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
                print(f"🧹 Cleaned: {temp_path}")
            except:
                pass

@app.get("/")
async def root():
    return {
        "message": "Enhanced Resume Analyzer API", 
        "version": "2.0.0",
        "description": "Extracts structured JSON data from resumes",
        "endpoints": {
            "analyze_resume": "POST /analyze-resume",
            "health": "GET /health",
            "docs": "GET /docs"
        }
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0"
    }

@app.get("/profiles")
async def get_profiles(limit: int = 10):
    """Get analyzed profiles from database"""
    return {
        "profiles": [], 
        "total": 0, 
        "message": "Database storage is disabled in this deployment"
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    reload_flag = os.environ.get("DEV_RELOAD", "false").lower() in ("1", "true", "yes")
    uvicorn.run(app, host="0.0.0.0", port=port, reload=reload_flag)
