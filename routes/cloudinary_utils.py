import cloudinary
import cloudinary.uploader
import cloudinary.api
from routes.config import Config
import secrets
import os
from werkzeug.utils import secure_filename

# Configure Cloudinary
cloudinary.config(
    cloud_name=Config.CLOUDINARY_CLOUD_NAME,
    api_key=Config.CLOUDINARY_API_KEY,
    api_secret=Config.CLOUDINARY_API_SECRET
)

def upload_course_thumbnail(file):
    """Upload course thumbnail to Cloudinary and return URL"""
    try:
        # Generate unique filename
        filename = secure_filename(file.filename)
        unique_filename = f"course_thumbnail_{secrets.token_hex(8)}_{filename}"
        
        # Upload to Cloudinary
        result = cloudinary.uploader.upload(
            file,
            public_id=f"course_thumbnails/{unique_filename}",
            folder="course_thumbnails",
            overwrite=True,
            resource_type="image",
            transformation=[
                {'width': 400, 'height': 300, 'crop': 'fill'},
                {'quality': 'auto'},
                {'format': 'webp'}
            ]
        )
        
        return result['secure_url']
    
    except Exception as e:
        print(f"Cloudinary upload error: {e}")
        return None

def delete_cloudinary_image(image_url):
    """Delete image from Cloudinary"""
    try:
        # Extract public_id from URL
        if 'course_thumbnails' in image_url:
            public_id = image_url.split('/')[-1].split('.')[0]
            result = cloudinary.uploader.destroy(f"course_thumbnails/{public_id}")
            return result.get('result') == 'ok'
        return False
    except Exception as e:
        print(f"Cloudinary delete error: {e}")
        return False