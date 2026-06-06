import streamlit as st
from utils import listar_arquivos_drive

def render_midias():
    st.markdown("### 🖼️ Portal de Mídias (Google Drive)")
    
    if "gcp_service_account" not in st.secrets or "DRIVE_FOLDER_IDS" not in st.secrets:
        st.warning("⚠️ O sistema ainda não possui a configuração de acesso ao Google Drive nos Secrets.")
    else:
        # Puxa os IDs das pastas configuradas nos Secrets
        folder_ids = st.secrets.get("DRIVE_FOLDER_IDS", [])
        
        with st.spinner("Buscando arquivos..."):
            arquivos = listar_arquivos_drive(folder_ids)
            
        if not arquivos: 
            st.info("Nenhum arquivo encontrado nas pastas configuradas.")
        else:
            st.success(f"Foram encontrados {len(arquivos)} arquivos.")
            cols = st.columns(4)
            for i, f in enumerate(arquivos):
                with cols[i % 4]:
                    st.markdown("<div class='media-card'>", unsafe_allow_html=True)
                    
                    if 'image' in f.get('mimeType', '') and 'thumbnailLink' in f:
                        st.markdown(f"<img src='{f['thumbnailLink']}' class='media-img'>", unsafe_allow_html=True)
                    else: 
                        st.markdown("📄 *(Documento/Vídeo)*")
                        
                    st.markdown(f"<div class='media-title'>{f['name']}</div>", unsafe_allow_html=True)
                    
                    if 'webContentLink' in f: 
                        st.link_button("📥 Baixar", f['webContentLink'], use_container_width=True)
                    elif 'webViewLink' in f: 
                        st.link_button("👁️ Abrir", f['webViewLink'], use_container_width=True)
                        
                    st.markdown("</div>", unsafe_allow_html=True)
