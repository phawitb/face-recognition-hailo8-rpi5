import socket
import numpy as np
import cv2
import json
import streamlit as st
from PIL import Image
import os
import csv
import time
import pandas as pd
import datetime
import base64
import threading

st.set_page_config(layout="wide", initial_sidebar_state="collapsed")
with open( "run/style.css" ) as css:
    st.markdown( f'<style>{css.read()}</style>' , unsafe_allow_html= True)

PERSON_DATA_PATH = "resources/person_data.csv"
FILE_HISTORY_PATH = f'historys/history_data.csv'

def img_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    data_url = f"data:image/png;base64,{encoded_string}"

    return data_url

def sort_max_area_index(objd):
    areas = []
    
    for i, obj in enumerate(objd):
        bbox = obj[2]  # Get bounding box
        x_min, y_min, x_max, y_max = bbox
        
        if x_max > x_min and y_max > y_min:
            area = (x_max - x_min) * (y_max - y_min)
            areas.append((i, area))  # Store index and area as a tuple
        else:
            raise ValueError(f"Invalid bounding box dimensions at index {i}: {bbox}")
    
    sorted_indices = sorted(areas, key=lambda x: x[1], reverse=True)
    
    return [index for index, area in sorted_indices]

def crop_to_aspect_ratio(image, aspect_width, aspect_height):
    height, width = image.shape[:2]
    original_area = width * height
    desired_ratio = aspect_width / aspect_height

    if width / height > desired_ratio:
        new_width = int(height * desired_ratio)
        new_height = height
    else:
        new_width = width
        new_height = int(width / desired_ratio)
    
    x_start = (width - new_width) // 2
    y_start = (height - new_height) // 2
    x_end = x_start + new_width
    y_end = y_start + new_height
    
    cropped_image = image[y_start:y_end, x_start:x_end]
    cropped_area = new_width * new_height
    change_ratio = cropped_area / original_area

    return cropped_image, change_ratio

def get_person_data(file_path, face_id):
    with open(file_path, mode='r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['face_id'] == face_id:
                return dict(row)

    return None

def create_hist_table():
    os.makedirs(os.path.dirname(FILE_HISTORY_PATH), exist_ok=True)
    df = pd.read_csv(FILE_HISTORY_PATH)
    person_ids = []
    names = []
    positions = []
    datetimes = []
    for index,row in df.iterrows():
        person_data_dict = get_person_data(PERSON_DATA_PATH, row['face_id'])
        person_ids.append(person_data_dict['person_id'])
        names.append(person_data_dict['name'])
        positions.append(person_data_dict['position'])

        dt = datetime.datetime.fromtimestamp(row['datetime'])
        dt_str = dt.strftime('%Y-%m-%d %H:%M:%S.%f')
        datetimes.append(dt_str)

    df['person_id'] = person_ids
    df['name'] = names
    df['position'] = positions
    df['datetime'] = datetimes

    df = df.sort_values(by='datetime',ascending=False)
    df.drop(columns=['face_id'], inplace=True)
    df = df[['datetime','person_id','name','position','img_path']]
    df = df.reset_index()

    return df

def alarmServer(base64_frame,face_id):
    print('\nsent to server ::::',base64_frame,face_id)

def save_data(save_history,frame):
    time_now = time.time()
    img_path = f'historys/images/{time_now}.jpg'
    os.makedirs(os.path.dirname(img_path), exist_ok=True)

    cv2.imwrite(img_path,frame)

    save_history['img_path'] = img_path
    save_history['datetime'] = time_now

    file_exists = os.path.exists(FILE_HISTORY_PATH)
    with open(FILE_HISTORY_PATH, mode="a", newline="") as file:
        writer = csv.writer(file)
        if not file_exists:
            header = save_history.keys()
            writer.writerow(header)
        writer.writerow(save_history.values())

    base64_frame = img_to_base64(img_path)
    alarmServer(base64_frame,save_history['face_id'])

def receiver():
    host = '127.0.0.1' 
    port = 65432        

    col1, col2 = st.columns([2,1])
    
    with col1:
        video_placeholder = st.empty()
        col_his = st.columns(5) 

        img_placeholders = [col_his[i].empty() for i in range(len(col_his))]

        if os.path.exists(FILE_HISTORY_PATH):
            df = create_hist_table()
            for index, row in df.iterrows():
                if index < 5:
                    datetime_str = datetime.datetime.strptime(row['datetime'], "%Y-%m-%d %H:%M:%S.%f").strftime("%d/%m/%y %H:%M:%S")
                    img_placeholders[index].image(row['img_path'],f"{datetime_str} {row['name']}")
                else:
                    break

    with col2:
        face_image_placeholder = st.empty()
        person_name_placeholder = st.empty()
        

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, port))
        s.listen()
        
        while True:
            conn, addr = s.accept()
            with conn:
                last_face_id_max = None
                refresh_show_history = False
                while True:
                    try:
                        json_size_data = conn.recv(4)
                        if not json_size_data:
                            break
                        json_size = int.from_bytes(json_size_data, byteorder='big')
                        json_data = conn.recv(json_size).decode()
                        metadata = json.loads(json_data)

                        print('metadata:::::',metadata)

                        face_id_max = None
                        save_history = False
                        if metadata['obj_detection']:
                            try:
                                idx_maxs = sort_max_area_index(metadata['obj_detection'])
                            
                                face_ids = []
                                for idx_max in idx_maxs:
                                    face_id = metadata["face_detected"][idx_max][0]
                                    face_ids.append(face_id)

                            except:
                                face_ids = [None]

                            if refresh_show_history and not [x for x in face_ids if x]:
                                df = create_hist_table()
                                for index, row in df.iterrows():
                                    if index < 5:
                                        datetime_str = datetime.datetime.strptime(row['datetime'], "%Y-%m-%d %H:%M:%S.%f").strftime("%d/%m/%y %H:%M:%S")
                                        img_placeholders[index].image(row['img_path'],f"{datetime_str} {row['name']}")

                                        face_image_placeholder.write("")
                                        person_name_placeholder.subheader("Please scan your face!")
                                    else:
                                        break 
                                refresh_show_history = False
                            
                            if face_ids[0]:
                                face_id_max = face_ids[0]
                                if face_id_max != last_face_id_max:

                                    save_history = {'face_id' : face_id_max}

                                    face_data = get_person_data(PERSON_DATA_PATH, face_id_max)
                                    face_image_path = f"resources/faces/{face_id_max}.png"
                                    face_image_placeholder.image(face_image_path, use_container_width=True)

                                    person_name_placeholder.markdown(f"""
                                    #### Name : {face_data['name']}
                                    #### ID : {face_data['person_id']}
                                    #### Position : {face_data['position']}
                                    """)

                            i = 0
                            for face_id in face_ids:
                                if face_id:
                                    face_data = get_person_data(PERSON_DATA_PATH, face_id)
                                    face_image_path = f"resources/faces/{face_id}.png"
                                    img_placeholders[i].image(face_image_path,f"{face_data['name']} {face_data['person_id']} {face_data['position']}")
                                    i += 1

                                    refresh_show_history = True
                            if i != 0:
                                while i < 5:
                                    img_placeholders[i].write("")
                                    i += 1

                        else:
                            face_image_placeholder.write("")
                            person_name_placeholder.subheader("Please scan your face!")

                            if refresh_show_history:
                                
                                df = create_hist_table()
                                for index, row in df.iterrows():
                                    if index < 5:
                                        datetime_str = datetime.datetime.strptime(row['datetime'], "%Y-%m-%d %H:%M:%S.%f").strftime("%d/%m/%y %H:%M:%S")
                                        img_placeholders[index].image(row['img_path'],f"{datetime_str} {row['name']}")
                                    else:
                                        break 
                                refresh_show_history = False

                        last_face_id_max = face_id_max

                        # Receive Data
                        frame_size_data = conn.recv(4)
                        if not frame_size_data:
                            break
                        frame_size = int.from_bytes(frame_size_data, byteorder='big')

                        frame_data = b""
                        while len(frame_data) < frame_size:
                            remaining_data = conn.recv(frame_size - len(frame_data))
                            if not remaining_data:
                                break
                            frame_data += remaining_data

                        # Decode the frame
                        nparr = np.frombuffer(frame_data, np.uint8)
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if frame is not None:
                            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            if save_history:
                                thread = threading.Thread(target=save_data, args=(save_history, frame))
                                thread.start()

                                # save_history_done = False
                                                            
                            img = Image.fromarray(frame_rgb)
                            with col1:
                                video_placeholder.image(img, use_container_width=True)
            
                    except Exception as e:
                        st.error(f"Error: {e}")
                        st.write(metadata)

if __name__ == "__main__":
    receiver()
