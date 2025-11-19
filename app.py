# app.py - ENHANCED JSON STRUCTURE VERSION
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

# Database integration removed — API-only deployment. If you need DB storage,
# re-add `get_db_connection()` and restore the insert block in `analyze_resume`.

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
        return {}

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
    phone_label = re.search(r'(Phone|Tel|Mobile|Mob)[:\s]*([+\d][\d\-\.\s\(\)]{6,})', text, re.IGNORECASE)
    if phone_label:
        info["phone"] = phone_label.group(2).strip()
    else:
        # Broad phone number patterns (support short local numbers)
        phone_patterns = [
            r'(?:\+?\d{1,3}[-.\s]?)?(?:\d{2,4}[-.\s]?){2,4}\d+',
            r'\b\d{7,12}\b'
        ]
        for pattern in phone_patterns:
            phone_match = re.search(pattern, text)
            if phone_match:
                candidate = phone_match.group().strip()
                # avoid capturing long year ranges or standalone years
                if not re.match(r'^(19|20)\d{2}$', candidate):
                    info["phone"] = candidate
                    break
    
    # Extract LinkedIn
    linkedin_match = re.search(r'(linkedin\.com/in/|linkedin\.com/company/)[^\s]+', text)
    if linkedin_match:
        info["linkedin"] = linkedin_match.group()
    
    github_match = re.search(r'github\.com/[^\s]+', text)
    if github_match:
        info["github"] = github_match.group()
    
    portfolio_match = re.search(r'((https?://|www\.)[\w\-\.\~:/?#@!$&\'"\(\)\*\+,;=%]+)', text)
    if portfolio_match:
        candidate = portfolio_match.group(1).strip()
        if '@' not in candidate and 'linkedin' not in candidate and 'github' not in candidate:
            info["portfolio"] = candidate

    address_tokens = ['address', 'location', 'residence', 'city', 'province', 'district', 'village', 'commune', 'street', 'st.', 'road', 'rd.', 'p.o. box', 'po box']
    for line in lines[:12]:
        low = line.strip().lower()
        if any(tok in low for tok in address_tokens) and len(line.strip()) > 5:
            info["location"] = line.strip()
            info["address"] = line.strip()
            break

    if not info["location"]:
        country_match = re.search(r'\b(Cambodia|Cambodian|Phnom\s*Penh|Kampot|Siem\s*Reap|Battambang|Sihanouk|Kandal|Kampong|Kep|Preah Vihear)\b', text, re.IGNORECASE)
        if country_match:
            info["location"] = country_match.group().strip()

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
                    # 2) If line contains common institution words, try to capture them as company
                    inst_match = re.search(r'([A-Z][\w\s&\-\.,\'"\(\)]+\b(Hospital|Center|Clinic|Institute|University|Ltd|Limited|Company|Corp|Corporation|School)\b)', line_clean)
                    if inst_match:
                        current_job = {
                            "company_name": inst_match.group(0).strip(),
                            "job_title": re.sub(inst_match.group(0), '', line_clean).strip(' ,-\u2013\u2014'),
                            "start_date": "",
                            "end_date": "",
                            "duration": "",
                            "responsibilities": []
                        }
                    else:
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

                # Extract dates if present (try to find ranges like 2015-2016 or '2015 - Present')
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
                # Detect if this line is actually the start of a new job/company header.
                header_indicators = ['hospital','center','clinic','institute','university','school','company','corp','corporation','department','centre','national']
                looks_like_header = False

                # If the line contains a year and also an institution word or date-range, treat as header
                if re.search(r'(19|20)\d{2}', line_clean):
                    if any(ind in line_clean.lower() for ind in header_indicators) or re.search(r'\(\d{4}[-–]\d{4}\)', line_clean) or re.search(r'\d{4}\s*[-–]\s*\d{4}', line_clean):
                        looks_like_header = True

                # Short lines with institution words (e.g., 'National Pediatric Hospital (2014-2015)')
                if not looks_like_header:
                    if len(line_clean.split()) <= 8 and any(ind in line_clean.lower() for ind in header_indicators) and re.search(r'(19|20)\d{2}', line_clean):
                        looks_like_header = True

                if looks_like_header:
                    # finalize previous job and start a new one from this header line
                    experience.append(current_job)
                    current_job = {}
                    header_line = re.sub(r'^[\-•\*\s]+', '', line_clean)
                    # extract and remove date range tokens
                    date_match = re.search(r'(\(?(?:\d{4}|\d{1,2}/\d{4})(?:\s*[-–to]+\s*(?:\d{4}|\d{1,2}/\d{4}))\)?)', header_line)
                    date_str = ''
                    duration_val = ''
                    if date_match:
                        date_str = date_match.group(0)
                        header_line = header_line.replace(date_str, '')
                        dur = re.search(r'(\d{4}\s*[-–]\s*\d{4}|\d{4})', date_str)
                        if dur:
                            duration_val = dur.group(0)

                    # Try 'Title at Company' pattern
                    if re.search(r'\bat\b', header_line, re.IGNORECASE):
                        parts_at = re.split(r'\bat\b', header_line, flags=re.IGNORECASE)
                        if len(parts_at) >= 2:
                            title_part = parts_at[0].strip()
                            company_part = parts_at[1].strip()
                            current_job = {
                                "company_name": company_part,
                                "job_title": title_part,
                                "start_date": "",
                                "end_date": "",
                                "duration": duration_val,
                                "responsibilities": []
                            }
                            date_vals = re.findall(r'(19|20)\d{2}', date_str)
                            if date_vals:
                                if len(date_vals) >= 1:
                                    current_job["start_date"] = date_vals[0] + "-01"
                                if len(date_vals) >= 2:
                                    current_job["end_date"] = date_vals[1] + "-01"
                            continue

                    # Institution-style match
                    inst_match = re.search(r'([A-Z][\w\s&\-\.,\'"\(\)]+\b(Hospital|Center|Clinic|Institute|University|Ltd|Limited|Company|Corp|Corporation|School)\b)', header_line)
                    if inst_match:
                        comp = inst_match.group(0).strip()
                        title_guess = re.sub(re.escape(comp), '', header_line).strip(' ,:-')
                        current_job = {
                            "company_name": comp,
                            "job_title": title_guess,
                            "start_date": "",
                            "end_date": "",
                            "duration": duration_val,
                            "responsibilities": []
                        }
                        date_vals = re.findall(r'(19|20)\d{2}', date_str)
                        if date_vals:
                            if len(date_vals) >= 1:
                                current_job["start_date"] = date_vals[0] + "-01"
                            if len(date_vals) >= 2:
                                current_job["end_date"] = date_vals[1] + "-01"
                        continue

                    # Fallback split on separators
                    parts = re.split(r'[|\-•,\u2013\u2014:]', header_line)
                    if len(parts) >= 2:
                        comp_guess = parts[0].strip()
                        title_guess = parts[1].strip()
                        current_job = {
                            "company_name": comp_guess,
                            "job_title": title_guess,
                            "start_date": "",
                            "end_date": "",
                            "duration": duration_val,
                            "responsibilities": []
                        }
                        date_vals = re.findall(r'(19|20)\d{2}', date_str)
                        if date_vals:
                            if len(date_vals) >= 1:
                                current_job["start_date"] = date_vals[0] + "-01"
                            if len(date_vals) >= 2:
                                current_job["end_date"] = date_vals[1] + "-01"
                        continue

                    # otherwise, do not append this as a responsibility
                    continue

                # Collect responsibilities (bullet points or descriptive lines)
                if (line_clean.startswith('•') or line_clean.startswith('-') or 
                    (len(line_clean) > 20 and not re.search(r'(19|20)\d{2}', line_clean))):
                    responsibility = re.sub(r'^[•\-]\s*', '', line_clean)
                    if len(responsibility) > 10:
                        current_job["responsibilities"].append(responsibility)

                # Save job if we hit next job entry or section end
                if (i + 1 < len(lines) and 
                    (re.search(r'(19|20)\d{2}', lines[i + 1]) or 
                     any(keyword in lines[i + 1].lower() for keyword in ['education', 'skills']))):
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
                if any(degree in line_clean.lower() for degree in ['bachelor', 'master', 'phd', 'associate', 'diploma', 'degree','majoring']):
                    current_edu = {
                        "degree": "",
                        "major": "",
                        "school_name": "",
                        "start_date": "",
                        "end_date": "",
                        "gpa": ""
                    }
                    
                    # Extract degree and school
                    if 'university' in line_clean.lower() or 'college' in line_clean.lower():
                        current_edu["school_name"] = line_clean
                    else:
                        current_edu["degree"] = line_clean
                    
                    # Extract dates
                    date_match = re.search(r'(19|20)\d{2}', line_clean)
                    if date_match:
                        current_edu["end_date"] = date_match.group() + "-01"
                    
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
            'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'go', 'rust', 
            'swift', 'kotlin', 'scala', 'r', 'php', 'ruby', 'perl'
        ],
        "web": [
            'html', 'css', 'react', 'angular', 'vue', 'node.js', 'express', 'django', 
            'flask', 'spring', 'laravel', 'jquery', 'bootstrap', 'sass', 'less'
        ],
        "data": [
            'sql', 'mysql', 'postgresql', 'mongodb', 'redis', 'oracle', 'sqlite',
            'pandas', 'numpy', 'tensorflow', 'pytorch', 'scikit-learn', 'keras',
            'tableau', 'power bi', 'data analysis', 'machine learning', 'deep learning'
        ],
        "devops": [
            'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'jenkins', 'gitlab',
            'terraform', 'ansible', 'ci/cd', 'linux', 'unix', 'bash', 'shell'
        ],
        "tools": [
            'git', 'github', 'gitlab', 'jira', 'confluence', 'docker', 'postman',
            'visual studio', 'eclipse', 'intellij', 'pycharm'
        ],
        "soft_skills": [
            'leadership', 'communication', 'teamwork', 'problem solving', 'critical thinking',
            'project management', 'agile', 'scrum', 'time management', 'adaptability'
        ]
    }
    
    text_lower = text.lower()
    
    for category, keywords in skill_categories.items():
        for keyword in keywords:
            if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
                # Normalize skill name
                normalized_name = keyword.title() if len(keyword) > 3 else keyword.upper()
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


def separate_projects_from_experience(work_experience: List[Dict[str, Any]]):
    """Move entries that look like projects out of work_experience into projects list."""
    project_keywords = ['project', 'analysis', 'machine learning', 'data analysis', 'analysis project', 'research', 'capstone']
    tech_keywords = ['python', 'java', 'javascript', 'react', 'node', 'sql', 'mongodb', 'aws', 'power bi', 'powerbi', 'mysql', 'pandas', 'numpy', 'php']

    cleaned_exp = []
    projects_from_exp = []

    date_like_re = re.compile(r'^(\d{1,2}/\d{4}|\d{4}/\d{1,2}|\d{4}(-|/)\d{2}|\d{1,2}-\d{4}|\d{2}/\d{2}/\d{4})$')

    for job in work_experience:
        title = (job.get('job_title') or '').lower()
        company = (job.get('company_name') or '').lower()
        responsibilities = job.get('responsibilities') or []

        # Heuristics: if title or company is date-like or empty and responsibilities include project keywords,
        # treat as project entry.
        resp_text = ' '.join(responsibilities).lower()
        has_project_kw = any(kw in title or kw in resp_text for kw in project_keywords)
        company_is_date = bool(date_like_re.search(company.strip())) if company else False
        title_is_date = bool(date_like_re.search(title.strip())) if title else False
        no_company = not company or company.strip() == ''

        if has_project_kw or (no_company and (title_is_date or company_is_date)) or (no_company and len(responsibilities) > 5 and any(kw in resp_text for kw in ['created', 'developed', 'built', 'collected', 'connected'])):
            # Build a project dict
            proj_title = job.get('job_title') or (responsibilities[0] if responsibilities else 'Project')
            proj_desc = '\n'.join(responsibilities)
            found_tech = list({k.title() for k in tech_keywords if re.search(r'\b' + re.escape(k) + r'\b', resp_text)})
            projects_from_exp.append({
                'title': proj_title,
                'description': proj_desc,
                'technologies': found_tech,
                'role': job.get('job_title', ''),
                'duration': job.get('duration', '')
            })
        else:
            cleaned_exp.append(job)

    return cleaned_exp, projects_from_exp

def split_combined_projects(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Split project entries that actually contain multiple projects into separate entries.

    Heuristics:
    - Look for lines in `description` that look like project headings: end with ':' or contain words
      like 'project', 'analysis', 'system', 'campaign', 'detection'.
    - Use these headings as split points; if title is date-like, prefer heading as title.
    - If no headings but description is long, split by blank-lines groups or by occurrences of
      known separators like '\n\n' or common subproject markers.
    """
    new_projects = []
    heading_kw = ['project', 'analysis', 'system', 'campaign', 'detection', 'study', 'experiment']
    for proj in projects:
        title = proj.get('title', '') or ''
        desc = proj.get('description', '') or ''
        lines = [ln.strip() for ln in desc.splitlines() if ln.strip()]

        # find candidate heading indices
        heading_indices = []
        for idx, ln in enumerate(lines):
            low = ln.lower()
            if ln.endswith(':') or any(kw in low for kw in heading_kw) or (len(ln.split()) <= 6 and ln.endswith('Project')):
                heading_indices.append(idx)

        # also consider lines that are Title Case and short (likely headings)
        for idx, ln in enumerate(lines):
            if idx in heading_indices:
                continue
            if 1 < len(ln.split()) <= 6 and ln[0].isupper() and ln.isalpha() == False:
                pass

        if heading_indices and len(heading_indices) > 0:

            heading_indices.append(len(lines))
            for i in range(len(heading_indices)-1):
                hidx = heading_indices[i]
                nextidx = heading_indices[i+1]
                hline = lines[hidx]
  
                ptitle = hline.rstrip(':').strip()
                pdesc = '\n'.join(lines[hidx+1:nextidx]).strip()
                if not pdesc:
                    pdesc = ''
                # detect tech
                resp_text = pdesc.lower()
                tech_keywords = ['python','java','javascript','react','node','sql','mongodb','aws','power bi','mysql','pandas','numpy','php','dax']
                found_tech = list({k.title() for k in tech_keywords if re.search(r'\b' + re.escape(k) + r'\b', resp_text)})
                new_projects.append({
                    'title': ptitle,
                    'description': pdesc,
                    'technologies': found_tech,
                    'role': proj.get('role',''),
                    'duration': proj.get('duration','')
                })
        else:
            raw = desc
            separators = ['\n\n', '\n- ', '\n• ', '\n\n\n']
            split_points = None
            for sep in separators:
                if sep in raw and raw.count(sep) > 1:
                    split_points = [s.strip() for s in raw.split(sep) if s.strip()]
                    break

            if split_points and len(split_points) > 1:
                for sp in split_points:
                    resp_text = sp.lower()
                    tech_keywords = ['python','java','javascript','react','node','sql','mongodb','aws','power bi','mysql','pandas','numpy','php','dax']
                    found_tech = list({k.title() for k in tech_keywords if re.search(r'\b' + re.escape(k) + r'\b', resp_text)})

                    first_line = sp.splitlines()[0]
                    ptitle = first_line if len(first_line) < 60 else (title or 'Project')
                    pdesc = sp
                    new_projects.append({
                        'title': ptitle,
                        'description': pdesc,
                        'technologies': found_tech,
                        'role': proj.get('role',''),
                        'duration': proj.get('duration','')
                    })
            else:
                # nothing to split — normalize title if it's a date-like placeholder
                if re.match(r'^(\d{1,2}/\d{4}|\d{4}/\d{1,2}|\d{4})$', title.strip()):
                    # try first good short line as title
                    candidate_title = ''
                    for ln in lines:
                        if len(ln.split()) <= 8 and len(ln) > 3 and not re.search(r'\b(\d{4}|\d{1,2}/\d{4})\b', ln):
                            candidate_title = ln
                            break
                    if candidate_title:
                        proj['title'] = candidate_title
                new_projects.append(proj)

    return new_projects

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
            
        # Add items to current section (skip phone-like lines)
        if current_section and len(line_clean) > 2:
            # skip if line is a phone/email or contains 'phone'
            if re.search(r'phone|tel|mobile|\b\d{7,12}\b', line_clean, re.IGNORECASE) or re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', line_clean):
                continue

            if current_section == "certifications":
                info["certifications"].append(line_clean)
            elif current_section == "languages":
                # Only accept known/common language names or language + proficiency patterns
                known_languages = ['english','khmer','french','chinese','spanish','arabic','japanese','korean','german','portuguese','hindi']
                lang_match = re.search(r'([A-Za-z]+)\s*(\(?(fluent|native|basic|intermediate|advanced)\)?)', line_clean, re.IGNORECASE)
                contains_known = any(re.search(r'\b' + re.escape(lang) + r'\b', line_clean.lower()) for lang in known_languages)
                if lang_match and contains_known:
                    info["languages"].append(line_clean)
                elif contains_known:
                    info["languages"].append(line_clean)
            elif current_section == "awards":
                info["awards"].append(line_clean)
    
    # Global scan for award-like phrases anywhere in the document (catch awards not under explicit heading)
    try:
        for m in re.finditer(r'([A-Z][^\n]{0,200}\b(award|awarded|received|winner|won|prize|recognition|honor|honoured|fellowship|scholarship)\b[^\.\n]{0,200})', text, re.IGNORECASE):
            snippet = m.group(0).strip()
            # Clean bullets and excessive whitespace
            snippet = re.sub(r'^[\-•\*\u2022\s]+', '', snippet)
            if snippet and snippet not in info["awards"]:
                info["awards"].append(snippet)
    except Exception:
        pass

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
        
        personal_info = extract_personal_info(resume_text)
        summary = extract_summary(resume_text)
        work_experience = extract_work_experience(resume_text)
        education = extract_education(resume_text)
        skills = extract_skills(resume_text)
        projects = extract_projects(resume_text)
        additional_info = extract_additional_info(resume_text)

        # Move project-like entries out of work_experience into projects
        try:
            work_experience, projects_from_exp = separate_projects_from_experience(work_experience)
            if projects_from_exp:
                projects.extend(projects_from_exp)
        except Exception:
            pass

        # After merging, split combined project blocks into individual projects
        try:
            projects = split_combined_projects(projects)
        except Exception:
            pass

        # Calculate experience metrics using cleaned work_experience
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
        
    
        
        print("Comprehensive analysis completed successfully")
        return ResumeAnalysisResponse(
            success=True,
            message="Resume analyzed successfully with structured data extraction",
            data=structured_data
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error: {e}")
        print(f"Stack trace: {traceback.format_exc()}")
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
            "profiles": "GET /profiles"
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
    try:
        return {"profiles": [], "total": 0, "message": "Database storage is disabled in this deployment"}
    except Exception as e:
        return {"profiles": [], "error": str(e)}
    finally:
        pass

if __name__ == "__main__":
    import uvicorn
    # For Render (and most cloud hosts), use the PORT env var they provide.
    # Disable reload by default in production; set DEV_RELOAD=true to enable.
    port = int(os.environ.get("PORT", 8001))
    reload_flag = os.environ.get("DEV_RELOAD", "false").lower() in ("1", "true", "yes")
    uvicorn.run(app, host="0.0.0.0", port=port, reload=reload_flag)