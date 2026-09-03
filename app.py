import streamlit as st
import pandas as pd
import requests
import boto3
from io import BytesIO
import uuid
import extra_streamlit_components as stx

st.set_page_config(page_title="Route Image Saver", layout="centered")

# Initialize cookie manager without cache to avoid warnings
if 'cookie_manager' not in st.session_state:
    st.session_state['cookie_manager'] = stx.CookieManager()
cookie_manager = st.session_state['cookie_manager']

st.title("🚚 Route Image Saver")
st.write("Upload your exported Excel sheet. This app will download the temporary images and save them permanently to AWS S3, returning a new sheet with permanent links.")

# Retrieve saved cookies
saved_access_key = cookie_manager.get(cookie="aws_access_key")
saved_secret_key = cookie_manager.get(cookie="aws_secret_key")
saved_bucket = cookie_manager.get(cookie="aws_bucket")
saved_region = cookie_manager.get(cookie="aws_region")

if saved_access_key is None: saved_access_key = ""
if saved_secret_key is None: saved_secret_key = ""
if saved_bucket is None: saved_bucket = ""
if saved_region is None: saved_region = "us-east-1"

# Sidebar for AWS settings
st.sidebar.header("AWS S3 Configuration")
st.sidebar.write("Enter your AWS credentials below. Save them to remember for next time!")

aws_access_key = st.sidebar.text_input("AWS Access Key ID", value=saved_access_key, type="password")
aws_secret_key = st.sidebar.text_input("AWS Secret Access Key", value=saved_secret_key, type="password")
aws_bucket = st.sidebar.text_input("S3 Bucket Name", value=saved_bucket)
aws_region = st.sidebar.text_input("AWS Region", value=saved_region)

if st.sidebar.button("Save to Browser"):
    cookie_manager.set("aws_access_key", aws_access_key)
    cookie_manager.set("aws_secret_key", aws_secret_key)
    cookie_manager.set("aws_bucket", aws_bucket)
    cookie_manager.set("aws_region", aws_region)
    st.sidebar.success("Credentials saved!")

uploaded_file = st.file_uploader("Upload Route Excel File (.xlsx)", type=["xlsx"])

if uploaded_file and aws_access_key and aws_secret_key and aws_bucket:
    if st.button("Process File"):
        try:
            # Read the uploaded Excel file
            df = pd.read_excel(uploaded_file)
            
            if 'Photos' not in df.columns:
                st.error("The uploaded file does not contain a 'Photos' column.")
            else:
                st.write(f"Found {len(df)} rows. Processing images...")
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Initialize AWS S3 Client
                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=aws_access_key,
                    aws_secret_access_key=aws_secret_key,
                    region_name=aws_region
                )
                
                new_links = []
                
                # Iterate through each row in the Excel file
                for index, row in df.iterrows():
                    photo_url = row.get('Photos')
                    order_id = str(row.get('Order ID', uuid.uuid4().hex[:8]))
                    
                    # Check if the photo URL is a valid string and starts with http
                    if pd.notna(photo_url) and isinstance(photo_url, str) and photo_url.startswith("http"):
                        status_text.text(f"Downloading image for Order {order_id}...")
                        try:
                            # 1. Download the image from the temporary link
                            response = requests.get(photo_url.strip(), timeout=15)
                            
                            if response.status_code == 200:
                                # 2. Generate a unique filename for S3
                                filename = f"delivery_photos/order_{order_id}_{uuid.uuid4().hex[:6]}.jpg"
                                
                                status_text.text(f"Uploading image for Order {order_id} to S3...")
                                
                                # 3. Upload the downloaded image to S3
                                s3_client.put_object(
                                    Bucket=aws_bucket,
                                    Key=filename,
                                    Body=response.content,
                                    ContentType="image/jpeg"
                                )
                                
                                # 4. Construct the permanent S3 URL
                                perm_url = f"https://{aws_bucket}.s3.{aws_region}.amazonaws.com/{filename}"
                                new_links.append(f'=HYPERLINK("{perm_url}", "View Photo")')
                            else:
                                st.warning(f"Could not download photo for Order {order_id}. Server returned status {response.status_code}.")
                                new_links.append(f'=HYPERLINK("{photo_url}", "View Photo")')
                        except Exception as e:
                            st.warning(f"Failed to process Order {order_id}: {e}")
                            new_links.append(f'=HYPERLINK("{photo_url}", "View Photo")')
                    else:
                        # If there is no photo or it's not a URL, leave it as is
                        new_links.append(photo_url)
                        
                    # Update progress bar
                    progress = (index + 1) / len(df)
                    progress_bar.progress(progress)
                    
                # Replace the old temporary links with the new permanent links
                df['Photos'] = new_links
                status_text.text("Processing complete! Preparing your download...")
                
                # Convert the updated dataframe back to an Excel file in memory
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                processed_data = output.getvalue()
                
                st.success("File processed successfully! All available images have been backed up.")
                
                # Provide a download button for the new file
                st.download_button(
                    label="⬇️ Download Updated Excel File",
                    data=processed_data,
                    file_name="permanent_links_route.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
        except Exception as e:
            st.error(f"An error occurred: {e}")
elif uploaded_file:
    st.info("Please fill in your AWS S3 Configuration in the sidebar on the left to proceed.")
