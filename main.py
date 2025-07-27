import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import io
import re
import asyncio
import time

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')

#Validate token exists
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required!")


# Menu configurations
MENUS = {
    'main': {
        'text': "🤖 *Selamat datang di VCF Generator Bot!*\n\nPilih menu di bawah ini:",
        'buttons': [
            [InlineKeyboardButton("📝 TEXT TO VCF", callback_data='text_to_vcf'), InlineKeyboardButton("📁 CV TXT TO VCF", callback_data='cv_txt_to_vcf')],
            [InlineKeyboardButton("🔄 CV VCF TO TXT", callback_data='cv_vcf_to_txt'), InlineKeyboardButton("🔗 MERGE TXT/VCF", callback_data='merge_files')]
        ]
    },
    'cv_submenu': {
        'text': "📁 *CV TXT TO VCF - Pilih Mode:*\n\n🔧 *V1* - Upload TXT, pilih output mode (Default/Custom)\n🚀 *V2* - Upload TXT dengan format batch otomatis",
        'buttons': [
            [InlineKeyboardButton("🔧 V1", callback_data='cv_v1'), InlineKeyboardButton("🚀 V2", callback_data='cv_v2')],
            [InlineKeyboardButton("⬅️ Back", callback_data='back_to_main')]
        ]
    },
    'merge_submenu': {
        'text': "🔗 *MERGE TXT/VCF - Pilih Jenis File:*\n\n📄 *TXT* - Gabung beberapa file TXT menjadi satu\n📋 *VCF* - Gabung beberapa file VCF menjadi satu",
        'buttons': [
            [InlineKeyboardButton("📄 TXT", callback_data='merge_txt'), InlineKeyboardButton("📋 VCF", callback_data='merge_vcf')],
            [InlineKeyboardButton("⬅️ Back", callback_data='back_to_main')]
        ]
    },
    'output_mode_selection': {
        'text': "🎉 *Upload Complete!*\n\n📋 *Pilih mode output:*\n\n🔹 **Default** - Nama file VCF sama dengan file TXT\n🔹 **Custom** - Nama file VCF sesuai input Anda\n\n*Pilih mode yang Anda inginkan:*",
        'buttons': [
            [InlineKeyboardButton("🔹 Default", callback_data='output_default'), InlineKeyboardButton("🎨 Custom", callback_data='output_custom')]
        ]
    },
    'v2_confirm': {
        'text': "🚀 *Mode V2 - Konfirmasi*\n\n📋 *Detail:*\n{details}\n\n*Lanjutkan proses?*",
        'buttons': [
            [InlineKeyboardButton("✅ Lanjutkan", callback_data='v2_proceed'), InlineKeyboardButton("❌ Batal", callback_data='back_to_main')]
        ]
    },
    'vcf_to_txt_selection': {
        'text': "🔄 *VCF TO TXT - Pilih Output:*\n\n📋 *Detail:*\n{details}\n\n*Pilih mode konversi:*",
        'buttons': [
            [InlineKeyboardButton("📄 Selesai", callback_data='vcf_separate'), InlineKeyboardButton("🔗 Gabung", callback_data='vcf_merge')]
        ]
    },
    'text_instruction': "📝 *Format input:*\n```\nnama_file_vcf\n\nnama kontak\nnomer telepon\n\nnama kontak\nnomer telepon\n```",
    'cv_instruction': "📁 *Upload file TXT Anda*\n\n• Upload satu atau beberapa file sekaligus\n• Bot akan otomatis mendeteksi ketika upload selesai",
    'v2_instruction': "🚀 *Mode V2 - Upload File TXT*\n\n📂 *Upload 1-10 file TXT*\n• **1 file**: Input manual format\n• **2-10 file**: Auto gabung & konfirmasi\n\n💡 *Bot akan otomatis memproses setelah upload selesai*",
    'vcf_instruction': "🔄 *Upload file VCF Anda*\n\n• Upload satu atau beberapa file VCF\n• Bot akan otomatis mendeteksi ketika upload selesai",
    'merge_txt_instruction': "🔗 *MERGE TXT - Upload File*\n\n📂 *Upload minimal 2 file TXT*\n• Bot akan menggabung semua file menjadi satu\n• Otomatis remove duplikat nomor telepon\n\n💡 *Bot akan memproses setelah upload selesai*",
    'merge_vcf_instruction': "🔗 *MERGE VCF - Upload File*\n\n📂 *Upload minimal 2 file VCF*\n• Bot akan menggabung semua kontak menjadi satu file\n• Otomatis remove duplikat kontak\n\n💡 *Bot akan memproses setelah upload selesai*"
}

def clean_name_for_vcf(name):
    """Clean name to be VCF compatible while preserving emojis"""
    cleaned = re.sub(r'[;\n\r]', ' ', name)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def parse_vcf_content(vcf_content):
    """Parse VCF content and extract contacts"""
    contacts = []
    vcards = re.findall(r'BEGIN:VCARD.*?END:VCARD', vcf_content, re.DOTALL)
    
    for vcard in vcards:
        name_match = re.search(r'FN:(.+)', vcard)
        tel_match = re.search(r'TEL:(.+)', vcard)
        
        if name_match and tel_match:
            name = name_match.group(1).strip()
            phone = tel_match.group(1).strip()
            contacts.append({'name': name, 'phone': phone})
    
    return contacts

def normalize_phone_for_txt_output(phone):
    """Normalize phone number for TXT output - only add + if missing, don't force Indonesian format"""
    phone = phone.strip()
    
    # If phone already starts with +, keep it as is
    if phone.startswith('+'):
        return phone
    
    # If phone doesn't start with +, just add + prefix without assuming country
    # Don't automatically convert to Indonesian format (+62)
    return '+' + phone

def create_txt_from_vcf(contacts):
    """Convert VCF contacts to TXT format (phone numbers only) with improved normalization"""
    if not contacts:
        return ""
    
    phone_numbers = []
    for contact in contacts:
        phone = normalize_phone_for_txt_output(contact['phone'])
        if phone not in phone_numbers:  # Avoid duplicates
            phone_numbers.append(phone)
    
    return '\n'.join(phone_numbers)

def normalize_phone_list_format(phone_list):
    """Normalize all phones in list to have consistent format"""
    if not phone_list:
        return phone_list
    
    # Check if any phone has + prefix
    has_plus = any(phone.startswith('+') for phone in phone_list)
    
    normalized_phones = []
    for phone in phone_list:
        if has_plus:
            # If any phone has +, make sure all have +
            if not phone.startswith('+'):
                if phone.startswith('0'):
                    phone = '+62' + phone[1:]
                elif phone.startswith('62'):
                    phone = '+' + phone
                else:
                    phone = '+62' + phone if len(phone) >= 10 else '+' + phone
        else:
            # If no phone has +, remove + from all
            if phone.startswith('+'):
                if phone.startswith('+62'):
                    phone = '0' + phone[3:]
                else:
                    phone = phone[1:]
        normalized_phones.append(phone)
    
    return normalized_phones

def merge_txt_files(txt_files_data):
    """Merge multiple TXT files and remove duplicates with consistent format"""
    all_phones = []
    phone_set = set()
    
    # Collect all phones first
    for file_data in txt_files_data:
        for phone in file_data['phone_numbers']:
            if phone not in phone_set:
                all_phones.append(phone)
                phone_set.add(phone)
    
    # Normalize format consistency
    normalized_phones = normalize_phone_list_format(all_phones)
    
    return normalized_phones

def merge_vcf_files(vcf_files_data):
    """Merge multiple VCF files and remove duplicates"""
    all_contacts = []
    contact_set = set()
    
    for file_data in vcf_files_data:
        for contact in file_data['contacts']:
            # Create unique identifier for contact (name + phone)
            contact_id = f"{contact['name']}|{contact['phone']}"
            if contact_id not in contact_set:
                all_contacts.append(contact)
                contact_set.add(contact_id)
    
    return all_contacts

def create_vcf_from_contacts(contacts):
    """Create VCF content from contact list"""
    vcf_content = ""
    for contact in contacts:
        vcf_content += f"BEGIN:VCARD\nVERSION:3.0\nFN:{contact['name']}\nTEL:{contact['phone']}\nEND:VCARD\n"
    return vcf_content

async def show_menu(message_target, menu_key, edit=False, **kwargs):
    """Show menu with configuration"""
    menu = MENUS[menu_key]
    text = menu['text'].format(**kwargs) if kwargs else menu['text']
    reply_markup = InlineKeyboardMarkup(menu['buttons']) if 'buttons' in menu else None
    
    if edit:
        await message_target.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await message_target.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await show_menu(update.message, 'main')

async def string_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data['waiting_for_string'] = True
    await update.message.reply_text(MENUS['text_instruction'], parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    handlers = {
        'text_to_vcf': lambda: setup_text_mode(query, context),
        'cv_txt_to_vcf': lambda: show_menu(query, 'cv_submenu', edit=True),
        'cv_vcf_to_txt': lambda: setup_vcf_to_txt_mode(query, context),
        'merge_files': lambda: show_menu(query, 'merge_submenu', edit=True),
        'merge_txt': lambda: setup_merge_txt_mode(query, context),
        'merge_vcf': lambda: setup_merge_vcf_mode(query, context),
        'cv_v1': lambda: setup_cv_v1_mode(query, context),
        'cv_v2': lambda: setup_cv_v2_mode(query, context),
        'output_default': lambda: setup_default_output(query, context),
        'output_custom': lambda: setup_custom_output(query, context),
        'v2_proceed': lambda: process_v2_batch(query, context),
        'vcf_separate': lambda: process_vcf_separate(query, context),
        'vcf_merge': lambda: setup_vcf_merge(query, context),
        'back_to_main': lambda: show_menu(query, 'main', edit=True)
    }
    
    if query.data in handlers:
        await handlers[query.data]()
    else:
        await query.edit_message_text("🚧 Fitur ini akan segera hadir!\n\nGunakan /start untuk kembali ke menu utama.", parse_mode='Markdown')

async def setup_text_mode(query, context):
    context.user_data.clear()
    context.user_data['waiting_for_string'] = True
    await query.edit_message_text(MENUS['text_instruction'], parse_mode='Markdown')

async def setup_cv_v1_mode(query, context):
    context.user_data.clear()
    context.user_data.update({
        'cv_mode': 'v1',
        'waiting_for_txt_files': True,
        'txt_files_data': [],
        'last_upload_time': time.time()
    })
    await query.edit_message_text(MENUS['cv_instruction'], parse_mode='Markdown')

async def setup_cv_v2_mode(query, context):
    context.user_data.clear()
    context.user_data.update({
        'cv_mode': 'v2',
        'waiting_for_txt_files': True,
        'txt_files_data': [],
        'last_upload_time': time.time()
    })
    await query.edit_message_text(MENUS['v2_instruction'], parse_mode='Markdown')

async def setup_vcf_to_txt_mode(query, context):
    context.user_data.clear()
    context.user_data.update({
        'waiting_for_vcf_files': True,
        'vcf_files_data': [],
        'last_upload_time': time.time()
    })
    await query.edit_message_text(MENUS['vcf_instruction'], parse_mode='Markdown')

async def setup_merge_txt_mode(query, context):
    context.user_data.clear()
    context.user_data.update({
        'merge_mode': 'txt',
        'waiting_for_merge_txt_files': True,
        'merge_txt_files_data': [],
        'last_upload_time': time.time()
    })
    await query.edit_message_text(MENUS['merge_txt_instruction'], parse_mode='Markdown')

async def setup_merge_vcf_mode(query, context):
    context.user_data.clear()
    context.user_data.update({
        'merge_mode': 'vcf',
        'waiting_for_merge_vcf_files': True,
        'merge_vcf_files_data': [],
        'last_upload_time': time.time()
    })
    await query.edit_message_text(MENUS['merge_vcf_instruction'], parse_mode='Markdown')

async def setup_default_output(query, context):
    context.user_data['output_mode'] = 'default'
    context.user_data['waiting_for_contact_name'] = True
    
    txt_files_data = context.user_data.get('txt_files_data', [])
    total_files = len(txt_files_data)
    total_phones = sum(len(f['phone_numbers']) for f in txt_files_data)
    
    summary = f"🔹 *Mode Default Dipilih*\n\n📋 *Detail File:*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for i, file_data in enumerate(txt_files_data[:10]):
        vcf_name = file_data['filename'].rsplit('.txt', 1)[0] + '.vcf'
        summary += f"📄 **{file_data['filename']}** → **{vcf_name}**\n"
    if total_files > 10:
        summary += f"📄 ... dan **{total_files - 10} file lainnya**\n"
    
    summary += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📁 **Total**: {total_files} file, {total_phones} nomor\n\n👤 **Ketik nama kontak untuk semua file VCF:**"
    
    await query.edit_message_text(summary, parse_mode='Markdown')

async def setup_custom_output(query, context):
    context.user_data['output_mode'] = 'custom'
    context.user_data['waiting_for_custom_filename'] = True
    
    txt_files_data = context.user_data.get('txt_files_data', [])
    total_files = len(txt_files_data)
    total_phones = sum(len(f['phone_numbers']) for f in txt_files_data)
    
    summary = f"🎨 *Mode Custom Dipilih*\n\n📋 *Detail:*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    summary += f"📁 **{total_files} file** akan diproses dengan {total_phones} nomor\n"
    summary += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n💡 **Contoh nama file:**\n"
    summary += f"• pudidi1 → pudidi1.vcf, pudidi2.vcf, ..., pudidi{total_files}.vcf\n"
    summary += f"• amanai-5 → amanai-5.vcf, amanai-6.vcf, ..., amanai-{4+total_files}.vcf\n\n"
    summary += f"📝 **Masukkan nama file (harus diakhiri angka):**"
    
    await query.edit_message_text(summary, parse_mode='Markdown')

async def process_vcf_separate(query, context):
    """Process VCF files separately"""
    vcf_files_data = context.user_data.get('vcf_files_data', [])
    
    processing_msg = await query.edit_message_text("🔄 Memproses konversi VCF ke TXT...")
    
    successful_files = 0
    total_processed = 0
    
    for file_data in vcf_files_data:
        filename = file_data['filename'].rsplit('.vcf', 1)[0] + '.txt'
        txt_content = create_txt_from_vcf(file_data['contacts'])
        
        if txt_content:
            txt_file = io.BytesIO(txt_content.encode('utf-8'))
            txt_file.name = filename
            await query.message.reply_document(document=txt_file, filename=filename)
            successful_files += 1
            total_processed += len(file_data['contacts'])
            await asyncio.sleep(0.3)
    
    try:
        await processing_msg.delete()
    except:
        pass
    
    summary = f"🎉 *VCF TO TXT SELESAI!*\n\n📊 *RINGKASAN:*\n━━━━━━━━━━━━━━━━━━━\n"
    summary += f"✅ *Berhasil: {successful_files} file*\n📞 *Total: {total_processed} kontak*\n"
    summary += f"━━━━━━━━━━━━━━━━━━━\n💡 Gunakan /start untuk konversi baru."
    
    await query.message.reply_text(summary, parse_mode='Markdown')
    context.user_data.clear()

async def setup_vcf_merge(query, context):
    """Setup VCF merge mode"""
    context.user_data['waiting_for_merge_filename'] = True
    
    vcf_files_data = context.user_data.get('vcf_files_data', [])
    total_files = len(vcf_files_data)
    total_contacts = sum(len(f['contacts']) for f in vcf_files_data)
    
    merge_text = f"🔗 *Mode Gabung Dipilih*\n\n📋 *Detail:*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    merge_text += f"📁 **{total_files} file VCF** akan digabung\n📞 **{total_contacts} kontak** total\n"
    merge_text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n📝 **Masukkan nama file TXT output:**"
    
    await query.edit_message_text(merge_text, parse_mode='Markdown')

def extract_phone_numbers(text: str) -> list:
    """Extract and clean phone numbers"""
    patterns = [r'\+?62\d{8,15}', r'0\d{8,15}', r'\+\d{10,15}', r'\d{10,15}']
    phones = []
    
    for pattern in patterns:
        for match in re.findall(pattern, text):
            clean = re.sub(r'[^\d+]', '', match)
            if 10 <= len(clean) <= 15 and len(set(clean.replace('+', ''))) >= 3:
                phones.append(clean)
    
    return list(dict.fromkeys(phones))

def normalize_phone(phone):
    """Normalize phone number format"""
    phone = phone.strip()
    if not phone.startswith('+'):
        if phone.startswith('0'):
            phone = '+62' + phone[1:]
        elif phone.startswith('62'):
            phone = '+' + phone
        else:
            phone = '+62' + phone if len(phone) >= 10 and not phone.startswith('1') else '+' + phone
    return phone

def create_vcf_content(text_input):
    """Convert text input to VCF format"""
    lines = [l.strip() for l in text_input.strip().split('\n')]
    if len(lines) < 3:
        return None, None, None
    
    filename = lines[0] + ('.vcf' if not lines[0].endswith('.vcf') else '')
    contact_blocks = [b.strip() for b in '\n'.join(lines[1:]).split('\n\n') if b.strip()]
    
    vcf_content = ""
    contact_stats = {}
    
    for block in contact_blocks:
        contact_lines = [l for l in block.split('\n') if l.strip()]
        if len(contact_lines) < 2:
            continue
            
        name_base = clean_name_for_vcf(contact_lines[0])
        phones = contact_lines[1:]
        contact_stats[name_base] = len(phones)
        
        for i, phone in enumerate(phones, 1):
            phone = normalize_phone(phone)
            name = f"{name_base} {i}" if len(phones) > 1 else name_base
            vcf_content += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL:{phone}\nEND:VCARD\n"
    
    return vcf_content, filename, contact_stats

def create_vcf_from_phones(phone_numbers: list, contact_name: str) -> str:
    """Create VCF from phone list"""
    contact_name = clean_name_for_vcf(contact_name)
    vcf_content = ""
    for i, phone in enumerate(phone_numbers, 1):
        phone = normalize_phone(phone)
        name = f"{contact_name} {i}" if len(phone_numbers) > 1 else contact_name
        vcf_content += f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL:{phone}\nEND:VCARD\n"
    return vcf_content

def generate_custom_filenames(base_name: str, total_files: int) -> list:
    """Generate custom filenames with incremental numbers"""
    match = re.search(r'(.+?)(\d+)$', base_name)
    if not match:
        return []
    
    base_part = match.group(1)
    start_number = int(match.group(2))
    
    return [f"{base_part}{start_number + i}.vcf" for i in range(total_files)]

def split_phones_into_batches(phones: list, contacts_per_file: int, total_files: int) -> list:
    """Split phone numbers into batches for V2 processing"""
    batches = []
    phones_per_batch = len(phones) // total_files
    remainder = len(phones) % total_files
    
    start_idx = 0
    for i in range(total_files):
        batch_size = min(contacts_per_file, phones_per_batch + (1 if i < remainder else 0))
        end_idx = start_idx + batch_size
        if end_idx > len(phones):
            end_idx = len(phones)
        batches.append(phones[start_idx:end_idx])
        start_idx = end_idx
        if start_idx >= len(phones):
            break
    
    return [batch for batch in batches if batch]

async def send_vcf_file(update, filename, vcf_content, stats_msg=None):
    """Send VCF file with optional caption"""
    vcf_file = io.BytesIO(vcf_content.encode('utf-8'))
    vcf_file.name = filename
    await update.message.reply_document(
        document=vcf_file, filename=filename,
        caption=stats_msg, parse_mode='Markdown' if stats_msg else None
    )

async def update_upload_status(update, context, file_count, file_type='txt'):
    """Update upload status message"""
    if file_type == 'txt':
        total_phones = sum(len(f['phone_numbers']) for f in context.user_data.get('txt_files_data', []))
        cv_mode = context.user_data.get('cv_mode', 'v1')
        
        if cv_mode == 'v2':
            message_text = f"📤 *Mode V2 - Menganalisis file...*\n\n✅ **{file_count} file** diproses\n📊 **{total_phones} nomor** ditemukan\n\n💡 *Menunggu file atau auto lanjut...*"
        else:
            message_text = f"📤 *Menganalisis file...*\n\n✅ **{file_count} file** berhasil diproses\n📊 **{total_phones} nomor** ditemukan\n\n💡 *Menunggu file selanjutnya atau otomatis lanjut...*"
    elif file_type == 'vcf':
        total_contacts = sum(len(f['contacts']) for f in context.user_data.get('vcf_files_data', []))
        message_text = f"📤 *Menganalisis file VCF...*\n\n✅ **{file_count} file** berhasil diproses\n📊 **{total_contacts} kontak** ditemukan\n\n💡 *Menunggu file selanjutnya atau otomatis lanjut...*"
    elif file_type == 'merge_txt':
        total_phones = sum(len(f['phone_numbers']) for f in context.user_data.get('merge_txt_files_data', []))
        message_text = f"📤 *MERGE TXT - Menganalisis file...*\n\n✅ **{file_count} file** diproses\n📊 **{total_phones} nomor** ditemukan\n\n💡 *Menunggu file atau auto lanjut...*"
    elif file_type == 'merge_vcf':
        total_contacts = sum(len(f['contacts']) for f in context.user_data.get('merge_vcf_files_data', []))
        message_text = f"📤 *MERGE VCF - Menganalisis file...*\n\n✅ **{file_count} file** diproses\n📊 **{total_contacts} kontak** ditemukan\n\n💡 *Menunggu file atau auto lanjut...*"
    
    if 'upload_status_message' in context.user_data:
        try:
            await context.user_data['upload_status_message'].edit_text(message_text, parse_mode='Markdown')
        except:
            pass
    else:
        context.user_data['upload_status_message'] = await update.message.reply_text(message_text, parse_mode='Markdown')

async def show_output_mode_selection(context):
    """Show output mode selection after upload completion"""
    txt_files_data = context.user_data.get('txt_files_data', [])
    total_files = len(txt_files_data)
    total_phones = sum(len(f['phone_numbers']) for f in txt_files_data)
    
    detailed_text = f"🎉 *Upload Complete!*\n\n📋 *Detail File:*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for i, file_data in enumerate(txt_files_data[:10]):
        detailed_text += f"📄 **{file_data['filename']}**: {len(file_data['phone_numbers'])} nomor\n"
    if total_files > 10:
        detailed_text += f"📄 ... dan **{total_files - 10} file lainnya**\n"
    
    detailed_text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📁 **Total**: {total_files} file, {total_phones} nomor\n\n"
    detailed_text += "📋 *Pilih mode output:*\n\n🔹 **Default** - Nama file VCF sama dengan file TXT\n🔹 **Custom** - Nama file VCF sesuai input Anda\n\n*Pilih mode yang Anda inginkan:*"
    
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔹 Default", callback_data='output_default'), InlineKeyboardButton("🎨 Custom", callback_data='output_custom')]
    ])
    
    if 'upload_status_message' in context.user_data:
        try:
            await context.user_data['upload_status_message'].edit_text(detailed_text, reply_markup=reply_markup, parse_mode='Markdown')
        except:
            pass

async def show_vcf_selection(context):
    """Show VCF output selection after upload completion"""
    vcf_files_data = context.user_data.get('vcf_files_data', [])
    total_files = len(vcf_files_data)
    total_contacts = sum(len(f['contacts']) for f in vcf_files_data)
    
    details = f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📁 **{total_files} file VCF** berhasil dianalisis\n📞 **{total_contacts} kontak** ditemukan\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Selesai", callback_data='vcf_separate'), InlineKeyboardButton("🔗 Gabung", callback_data='vcf_merge')]
    ])
    
    selection_text = f"🔄 *VCF TO TXT - Pilih Output:*\n\n📋 *Detail:*\n{details}\n\n*Pilih mode konversi:*"
    
    if 'upload_status_message' in context.user_data:
        try:
            await context.user_data['upload_status_message'].edit_text(selection_text, reply_markup=reply_markup, parse_mode='Markdown')
        except:
            pass

async def show_merge_txt_filename_request(context):
    """Show merge TXT filename request after upload completion"""
    merge_txt_files_data = context.user_data.get('merge_txt_files_data', [])
    total_files = len(merge_txt_files_data)
    merged_phones = merge_txt_files(merge_txt_files_data)
    total_phones = len(merged_phones)
    unique_phones = len(set(merged_phones))
    
    context.user_data['merged_phones'] = merged_phones
    context.user_data['waiting_for_merge_txt_filename'] = True
    
    merge_text = f"🔗 *MERGE TXT - Siap Digabung*\n\n📋 *Detail:*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    merge_text += f"📁 **{total_files} file TXT** akan digabung\n📊 **{total_phones} nomor** total\n📞 **{unique_phones} nomor** unik (duplikat dihapus)\n"
    merge_text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n📝 **Masukkan nama file TXT output:**"
    
    if 'upload_status_message' in context.user_data:
        try:
            await context.user_data['upload_status_message'].edit_text(merge_text, parse_mode='Markdown')
        except:
            pass

async def show_merge_vcf_filename_request(context):
    """Show merge VCF filename request after upload completion"""
    merge_vcf_files_data = context.user_data.get('merge_vcf_files_data', [])
    total_files = len(merge_vcf_files_data)
    merged_contacts = merge_vcf_files(merge_vcf_files_data)
    total_contacts = len(merged_contacts)
    original_total = sum(len(f['contacts']) for f in merge_vcf_files_data)
    
    context.user_data['merged_contacts'] = merged_contacts
    context.user_data['waiting_for_merge_vcf_filename'] = True
    
    merge_text = f"🔗 *MERGE VCF - Siap Digabung*\n\n📋 *Detail:*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    merge_text += f"📁 **{total_files} file VCF** akan digabung\n📊 **{original_total} kontak** total\n📞 **{total_contacts} kontak** unik (duplikat dihapus)\n"
    merge_text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n📝 **Masukkan nama file VCF output:**"
    
    if 'upload_status_message' in context.user_data:
        try:
            await context.user_data['upload_status_message'].edit_text(merge_text, parse_mode='Markdown')
        except:
            pass

async def show_v2_confirmation(context):
    """Show V2 confirmation for multiple files"""
    txt_files_data = context.user_data.get('txt_files_data', [])
    total_files = len(txt_files_data)
    total_phones = sum(len(f['phone_numbers']) for f in txt_files_data)
    
    details = f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📁 **{total_files} file** akan digabung\n📊 **{total_phones} nomor** total\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Lanjutkan", callback_data='v2_proceed'), InlineKeyboardButton("❌ Batal", callback_data='back_to_main')]
    ])
    
    confirmation_text = f"🚀 *Mode V2 - Konfirmasi*\n\n📋 *Detail:*\n{details}\n\n*Lanjutkan proses?*"
    
    if 'upload_status_message' in context.user_data:
        try:
            await context.user_data['upload_status_message'].edit_text(confirmation_text, reply_markup=reply_markup, parse_mode='Markdown')
        except:
            pass

async def show_v2_format_input(context, show_total=True):
    """Show V2 format input with total phone information"""
    if show_total:
        # Calculate total phones for information display
        if context.user_data.get('merged_phones'):
            total_phones = len(context.user_data['merged_phones'])
        else:
            txt_files_data = context.user_data.get('txt_files_data', [])
            if txt_files_data:
                if len(txt_files_data) == 1:
                    total_phones = len(txt_files_data[0]['phone_numbers'])
                else:
                    all_phones = []
                    for file_data in txt_files_data:
                        all_phones.extend(file_data['phone_numbers'])
                    total_phones = len(all_phones)
            else:
                total_phones = 0
        
        format_text = f"🚀 *Mode V2 - Format Input*\n\n📊 **INFORMASI PENTING:**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📞 **Total {total_phones} nomor** siap diproses\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n📝 *Masukkan format (pisahkan dengan koma):*\n```\nnama_kontak,nama_file,jumlah_kontak_perfile,jumlah_file,angka_awal\n```\n\n💡 *Contoh:* `pudidi,amanai,50,20,1`\n\n⚠️ *Pastikan jumlah_kontak_perfile × jumlah_file tidak melebihi {total_phones}*"
    else:
        format_text = f"🚀 *Mode V2 - Format Input*\n\n📝 *Masukkan format (pisahkan dengan koma):*\n```\nnama_kontak,nama_file,jumlah_kontak_perfile,jumlah_file,angka_awal\n```\n\n💡 *Contoh:* `pudidi,amanai,50,20,1`"
    
    if 'upload_status_message' in context.user_data:
        try:
            await context.user_data['upload_status_message'].edit_text(format_text, parse_mode='Markdown')
        except:
            pass

async def check_upload_completion(context):
    """Check if upload is complete and show next step"""
    if (time.time() - context.user_data.get('last_upload_time', 0) >= 3.0 and 
        context.user_data.get('waiting_for_txt_files') and
        context.user_data.get('txt_files_data')):
        
        cv_mode = context.user_data.get('cv_mode', 'v1')
        file_count = len(context.user_data.get('txt_files_data', []))
        
        if cv_mode == 'v2':
            if file_count == 1:
                context.user_data['waiting_for_txt_files'] = False
                context.user_data['waiting_for_v2_format'] = True
                await show_v2_format_input(context)
            else:
                await show_v2_confirmation(context)
                context.user_data['waiting_for_txt_files'] = False
        else:
            await show_output_mode_selection(context)
            context.user_data['waiting_for_txt_files'] = False
    
    elif (time.time() - context.user_data.get('last_upload_time', 0) >= 3.0 and 
          context.user_data.get('waiting_for_vcf_files') and
          context.user_data.get('vcf_files_data')):
        
        await show_vcf_selection(context)
        context.user_data['waiting_for_vcf_files'] = False
    
    elif (time.time() - context.user_data.get('last_upload_time', 0) >= 3.0 and 
          context.user_data.get('waiting_for_merge_txt_files') and
          context.user_data.get('merge_txt_files_data')):
        
        file_count = len(context.user_data.get('merge_txt_files_data', []))
        if file_count >= 2:
            await show_merge_txt_filename_request(context)
            context.user_data['waiting_for_merge_txt_files'] = False
    
    elif (time.time() - context.user_data.get('last_upload_time', 0) >= 3.0 and 
          context.user_data.get('waiting_for_merge_vcf_files') and
          context.user_data.get('merge_vcf_files_data')):
        
        file_count = len(context.user_data.get('merge_vcf_files_data', []))
        if file_count >= 2:
            await show_merge_vcf_filename_request(context)
            context.user_data['waiting_for_merge_vcf_files'] = False

async def process_v2_batch(query, context):
    """Process V2 batch for multiple files"""
    txt_files_data = context.user_data.get('txt_files_data', [])
    all_phones = []
    for file_data in txt_files_data:
        all_phones.extend(file_data['phone_numbers'])
    
    # Normalize format consistency for merged phones
    all_phones = normalize_phone_list_format(all_phones)
    
    context.user_data['merged_phones'] = all_phones
    context.user_data['waiting_for_v2_format'] = True
    
    await show_v2_format_input(context)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle TXT and VCF file uploads"""
    document = update.message.document
    
    # Handle TXT files for CV modes
    if (context.user_data.get('waiting_for_txt_files') and 
        context.user_data.get('cv_mode') in ['v1', 'v2'] and
        document.file_name.lower().endswith('.txt')):
        
        # Check file limit for V2 (changed from 5 to 10)
        if context.user_data.get('cv_mode') == 'v2' and len(context.user_data.get('txt_files_data', [])) >= 10:
            await update.message.reply_text("❌ Mode V2 maksimal 10 file!")
            return
        
        try:
            file = await context.bot.get_file(document.file_id)
            file_content = await file.download_as_bytearray()
            
            text_content = None
            for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    text_content = file_content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if not text_content:
                await update.message.reply_text(f"❌ Tidak dapat membaca file {document.file_name}")
                return
            
            phone_numbers = extract_phone_numbers(text_content)
            if not phone_numbers:
                await update.message.reply_text(f"❌ Tidak ditemukan nomor telepon dalam file {document.file_name}")
                return
            
            context.user_data['txt_files_data'].append({
                'filename': document.file_name,
                'phone_numbers': phone_numbers
            })
            context.user_data['last_upload_time'] = time.time()
            
            await update_upload_status(update, context, len(context.user_data['txt_files_data']), 'txt')
            asyncio.create_task(delayed_check(context))
            
        except Exception as e:
            logger.error(f"Error processing TXT file: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan saat memproses file TXT.")
    
    # Handle VCF files
    elif (context.user_data.get('waiting_for_vcf_files') and 
          document.file_name.lower().endswith('.vcf')):
        
        try:
            file = await context.bot.get_file(document.file_id)
            file_content = await file.download_as_bytearray()
            
            vcf_content = None
            for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    vcf_content = file_content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if not vcf_content:
                await update.message.reply_text(f"❌ Tidak dapat membaca file {document.file_name}")
                return
            
            contacts = parse_vcf_content(vcf_content)
            if not contacts:
                await update.message.reply_text(f"❌ Tidak ditemukan kontak dalam file {document.file_name}")
                return
            
            context.user_data['vcf_files_data'].append({
                'filename': document.file_name,
                'contacts': contacts
            })
            context.user_data['last_upload_time'] = time.time()
            
            await update_upload_status(update, context, len(context.user_data['vcf_files_data']), 'vcf')
            asyncio.create_task(delayed_check(context))
            
        except Exception as e:
            logger.error(f"Error processing VCF file: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan saat memproses file VCF.")
    
    # Handle TXT files for MERGE TXT mode
    elif (context.user_data.get('waiting_for_merge_txt_files') and 
          document.file_name.lower().endswith('.txt')):
        
        try:
            file = await context.bot.get_file(document.file_id)
            file_content = await file.download_as_bytearray()
            
            text_content = None
            for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    text_content = file_content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if not text_content:
                await update.message.reply_text(f"❌ Tidak dapat membaca file {document.file_name}")
                return
            
            phone_numbers = extract_phone_numbers(text_content)
            if not phone_numbers:
                await update.message.reply_text(f"❌ Tidak ditemukan nomor telepon dalam file {document.file_name}")
                return
            
            context.user_data['merge_txt_files_data'].append({
                'filename': document.file_name,
                'phone_numbers': phone_numbers
            })
            context.user_data['last_upload_time'] = time.time()
            
            await update_upload_status(update, context, len(context.user_data['merge_txt_files_data']), 'merge_txt')
            asyncio.create_task(delayed_check(context))
            
        except Exception as e:
            logger.error(f"Error processing MERGE TXT file: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan saat memproses file TXT untuk merge.")
    
    # Handle VCF files for MERGE VCF mode
    elif (context.user_data.get('waiting_for_merge_vcf_files') and 
          document.file_name.lower().endswith('.vcf')):
        
        try:
            file = await context.bot.get_file(document.file_id)
            file_content = await file.download_as_bytearray()
            
            vcf_content = None
            for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    vcf_content = file_content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if not vcf_content:
                await update.message.reply_text(f"❌ Tidak dapat membaca file {document.file_name}")
                return
            
            contacts = parse_vcf_content(vcf_content)
            if not contacts:
                await update.message.reply_text(f"❌ Tidak ditemukan kontak dalam file {document.file_name}")
                return
            
            context.user_data['merge_vcf_files_data'].append({
                'filename': document.file_name,
                'contacts': contacts
            })
            context.user_data['last_upload_time'] = time.time()
            
            await update_upload_status(update, context, len(context.user_data['merge_vcf_files_data']), 'merge_vcf')
            asyncio.create_task(delayed_check(context))
            
        except Exception as e:
            logger.error(f"Error processing MERGE VCF file: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan saat memproses file VCF untuk merge.")
    
    else:
        await update.message.reply_text("❌ Silakan gunakan menu untuk memulai proses konversi atau upload file dengan format yang benar.")

async def delayed_check(context):
    """Delayed upload completion check"""
    await asyncio.sleep(4.0)
    await check_upload_completion(context)

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for all modes"""
    user_input = update.message.text.strip()
    
    # TEXT TO VCF V1 mode
    if context.user_data.get('waiting_for_string'):
        try:
            vcf_content, filename, contact_stats = create_vcf_content(user_input)
            if not all([vcf_content, filename, contact_stats]):
                await update.message.reply_text(
                    "❌ Format tidak valid! Pastikan format:\n```\nnama_file\n\nnama kontak\nnomer telepon\n```",
                    parse_mode='Markdown'
                )
                return
            
            total_contacts = sum(contact_stats.values())
            stats_msg = f"✅ *File {filename} berhasil dibuat!*\n\n📊 *DETAIL:*\n━━━━━━━━━━━━━━━━━━━\n"
            for name, count in contact_stats.items():
                stats_msg += f"👤 {name}: {count} kontak\n"
            stats_msg += f"━━━━━━━━━━━━━━━━━━━\n🔢 *Total: {total_contacts} kontak*\n\n💡 Gunakan /start untuk konversi baru."
            
            await send_vcf_file(update, filename, vcf_content, stats_msg)
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Error processing VCF: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan saat memproses input.")
            context.user_data.clear()
    
    # V2 format input
    elif context.user_data.get('waiting_for_v2_format'):
        try:
            parts = [p.strip() for p in user_input.split(',')]
            if len(parts) != 5:
                await update.message.reply_text("❌ Format salah! Harus 5 parameter dipisah koma.\n\n💡 *Contoh:* `pudidi,amanai,50,20,1`")
                return
            
            contact_name, file_base, contacts_per_file, total_files, start_num = parts
            contacts_per_file, total_files, start_num = int(contacts_per_file), int(total_files), int(start_num)
            
            if contacts_per_file <= 0 or total_files <= 0:
                await update.message.reply_text("❌ Jumlah kontak dan file harus lebih dari 0!")
                return
            
            phones = context.user_data.get('merged_phones') or context.user_data['txt_files_data'][0]['phone_numbers']
            
            if len(phones) < contacts_per_file:
                await update.message.reply_text(f"❌ Tidak cukup nomor! Tersedia {len(phones)}, diminta {contacts_per_file} per file.")
                return
            
            processing_msg = await update.message.reply_text("🔄 Memproses file V2...")
            
            phone_batches = split_phones_into_batches(phones, contacts_per_file, total_files)
            
            successful_files = 0
            total_processed = 0
            
            for i, batch in enumerate(phone_batches):
                filename = f"{file_base}{start_num + i}.vcf"
                vcf_content = create_vcf_from_phones(batch, contact_name)
                
                if vcf_content:
                    await send_vcf_file(update, filename, vcf_content)
                    successful_files += 1
                    total_processed += len(batch)
                    await asyncio.sleep(0.3)
            
            try:
                await processing_msg.delete()
            except:
                pass
            
            summary = f"🎉 *V2 BATCH SELESAI!*\n\n📊 *RINGKASAN:*\n━━━━━━━━━━━━━━━━━━━\n"
            summary += f"✅ *Berhasil: {successful_files} file*\n"
            summary += f"👤 *Nama: {contact_name}*\n📞 *Total: {total_processed} kontak*\n"
            summary += f"📁 *Pattern: {file_base}{start_num}-{start_num + successful_files - 1}.vcf*\n"
            summary += f"━━━━━━━━━━━━━━━━━━━\n💡 Gunakan /start untuk konversi baru."
            
            await update.message.reply_text(summary, parse_mode='Markdown')
            context.user_data.clear()
            
        except ValueError:
            await update.message.reply_text("❌ Format angka salah! Pastikan jumlah kontak, file, dan angka adalah angka valid.")
        except Exception as e:
            logger.error(f"Error in V2 processing: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan saat memproses format V2.")
    
    # VCF merge filename input
    elif context.user_data.get('waiting_for_merge_filename'):
        filename = user_input.strip()
        if not filename:
            await update.message.reply_text("❌ Nama file tidak boleh kosong!")
            return
        
        if not filename.endswith('.txt'):
            filename += '.txt'
        
        try:
            processing_msg = await update.message.reply_text("🔄 Menggabung file VCF ke TXT...")
            
            vcf_files_data = context.user_data.get('vcf_files_data', [])
            all_contacts = []
            
            for file_data in vcf_files_data:
                all_contacts.extend(file_data['contacts'])
            
            merged_txt_content = create_txt_from_vcf(all_contacts)
            
            if merged_vcf_content:
                vcf_file = io.BytesIO(merged_vcf_content.encode('utf-8'))
                vcf_file.name = filename
                await update.message.reply_document(document=vcf_file, filename=filename)
            
            try:
                await processing_msg.delete()
            except:
                pass
            
            summary = f"🎉 *MERGE VCF SELESAI!*\n\n📊 *RINGKASAN:*\n━━━━━━━━━━━━━━━━━━━\n"
            summary += f"📁 *File: {filename}*\n📞 *Total: {len(merged_contacts)} kontak*\n"
            summary += f"━━━━━━━━━━━━━━━━━━━\n💡 Gunakan /start untuk konversi baru."
            
            await update.message.reply_text(summary, parse_mode='Markdown')
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Error in VCF merge: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan saat menggabung file VCF.")
            context.user_data.clear()
    
    # CV V1 - Contact name input for DEFAULT mode
    elif context.user_data.get('waiting_for_contact_name'):
        contact_name = clean_name_for_vcf(user_input)
        if not contact_name:
            await update.message.reply_text("❌ Nama kontak tidak valid!")
            return
        
        try:
            processing_msg = await update.message.reply_text("🔄 Memproses file VCF...")
            txt_files_data = context.user_data.get('txt_files_data', [])
            
            successful_files = 0
            total_processed = 0
            
            for file_data in txt_files_data:
                filename = file_data['filename'].rsplit('.txt', 1)[0] + '.vcf'
                # Normalize phone format consistency before creating VCF
                normalized_phones = normalize_phone_list_format(file_data['phone_numbers'])
                vcf_content = create_vcf_from_phones(normalized_phones, contact_name)
                
                if vcf_content:
                    await send_vcf_file(update, filename, vcf_content)
                    successful_files += 1
                    total_processed += len(normalized_phones)
                    await asyncio.sleep(0.3)
            
            try:
                await processing_msg.delete()
            except:
                pass
            
            summary = f"🎉 *DEFAULT MODE SELESAI!*\n\n📊 *RINGKASAN:*\n━━━━━━━━━━━━━━━━━━━\n"
            summary += f"✅ *Berhasil: {successful_files} file*\n"
            summary += f"👤 *Nama: {contact_name}*\n📞 *Total: {total_processed} kontak*\n"
            summary += f"━━━━━━━━━━━━━━━━━━━\n💡 Gunakan /start untuk konversi baru."
            
            await update.message.reply_text(summary, parse_mode='Markdown')
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Error processing default mode: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan saat memproses file.")
            context.user_data.clear()
    
# CV V1 - Custom filename input (STEP 1)
    elif context.user_data.get('waiting_for_custom_filename'):
        base_filename = user_input.strip()
        
        if not re.search(r'\d+', base_filename):
            await update.message.reply_text("❌ Nama file harus diakhiri dengan angka!\n\n💡 *Contoh:* `pudidi1` atau `amanai-5`")
            return
        
        try:
            txt_files_data = context.user_data.get('txt_files_data', [])
            total_files = len(txt_files_data)
            
            custom_filenames = generate_custom_filenames(base_filename, total_files)
            if not custom_filenames:
                await update.message.reply_text("❌ Gagal generate nama file custom!")
                return
            
            # Store custom filenames and change state to wait for contact name
            context.user_data['custom_filenames'] = custom_filenames
            context.user_data['waiting_for_custom_filename'] = False  # Stop waiting for filename
            context.user_data['waiting_for_custom_contact_name'] = True  # Start waiting for contact name
            
            total_phones = sum(len(f['phone_numbers']) for f in txt_files_data)
            
            preview_text = f"🎨 *Custom Filenames Generated!*\n\n📋 *Preview (5 pertama):*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for i, filename in enumerate(custom_filenames[:5]):
                preview_text += f"📄 **{txt_files_data[i]['filename']}** → **{filename}**\n"
            if total_files > 5:
                preview_text += f"📄 ... dan **{total_files - 5} file lainnya**\n"
            
            preview_text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📁 **Total**: {total_files} file, {total_phones} nomor\n\n👤 **Ketik nama kontak untuk semua file VCF:**"
            
            await update.message.reply_text(preview_text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error generating custom filenames: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan saat generate nama file.")
            context.user_data.clear()
    
    # MERGE TXT filename input
    elif context.user_data.get('waiting_for_merge_txt_filename'):
        filename = user_input.strip()
        if not filename:
            await update.message.reply_text("❌ Nama file tidak boleh kosong!")
            return
        
        if not filename.endswith('.txt'):
            filename += '.txt'
        
        try:
            processing_msg = await update.message.reply_text("🔄 Menggabung file TXT...")
            
            merged_phones = context.user_data.get('merged_phones', [])
            merged_txt_content = '\n'.join(merged_phones)
            
            if merged_txt_content:
                txt_file = io.BytesIO(merged_txt_content.encode('utf-8'))
                txt_file.name = filename
                await update.message.reply_document(document=txt_file, filename=filename)
            
            try:
                await processing_msg.delete()
            except:
                pass
            
            summary = f"🎉 *MERGE TXT SELESAI!*\n\n📊 *RINGKASAN:*\n━━━━━━━━━━━━━━━━━━━\n"
            summary += f"📁 *File: {filename}*\n📞 *Total: {len(merged_phones)} nomor*\n"
            summary += f"━━━━━━━━━━━━━━━━━━━\n💡 Gunakan /start untuk konversi baru."
            
            await update.message.reply_text(summary, parse_mode='Markdown')
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Error in TXT merge: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan saat menggabung file TXT.")
            context.user_data.clear()
    
 # MERGE VCF filename input
    elif context.user_data.get('waiting_for_merge_vcf_filename'):
        filename = user_input.strip()
        if not filename:
            await update.message.reply_text("❌ Nama file tidak boleh kosong!")
            return
        
        if not filename.endswith('.vcf'):
            filename += '.vcf'
        
        try:
            processing_msg = await update.message.reply_text("🔄 Menggabung file VCF...")
            
            merged_contacts = context.user_data.get('merged_contacts', [])
            merged_vcf_content = create_vcf_from_contacts(merged_contacts)
            
            if merged_vcf_content:
                vcf_file = io.BytesIO(merged_vcf_content.encode('utf-8'))
                vcf_file.name = filename
                await update.message.reply_document(document=vcf_file, filename=filename)
            
            try:
                await processing_msg.delete()
            except:
                pass
            
            summary = f"🎉 *VCF MERGE SELESAI!*\n\n📊 *RINGKASAN:*\n━━━━━━━━━━━━━━━━━━━\n"
            summary += f"📁 *File: {filename}*\n📞 *Total: {len(merged_contacts)} kontak*\n"
            summary += f"━━━━━━━━━━━━━━━━━━━\n💡 Gunakan /start untuk konversi baru."
            
            await update.message.reply_text(summary, parse_mode='Markdown')
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Error in VCF merge: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan saat menggabung file VCF.")
            context.user_data.clear()
    
    # CV V1 - Custom contact name input (STEP 2 - FINAL)
    elif context.user_data.get('waiting_for_custom_contact_name'):
        contact_name = clean_name_for_vcf(user_input)
        if not contact_name:
            await update.message.reply_text("❌ Nama kontak tidak valid!")
            return
        
        try:
            processing_msg = await update.message.reply_text("🔄 Memproses file custom VCF...")
            txt_files_data = context.user_data.get('txt_files_data', [])
            custom_filenames = context.user_data.get('custom_filenames', [])
            
            successful_files = 0
            total_processed = 0
            
            for i, file_data in enumerate(txt_files_data):
                if i < len(custom_filenames):
                    filename = custom_filenames[i]
                    # Normalize phone format consistency before creating VCF
                    normalized_phones = normalize_phone_list_format(file_data['phone_numbers'])
                    vcf_content = create_vcf_from_phones(normalized_phones, contact_name)
                    
                    if vcf_content:
                        await send_vcf_file(update, filename, vcf_content)
                        successful_files += 1
                        total_processed += len(normalized_phones)
                        await asyncio.sleep(0.3)
            
            try:
                await processing_msg.delete()
            except:
                pass
            
            summary = f"🎉 *CUSTOM MODE SELESAI!*\n\n📊 *RINGKASAN:*\n━━━━━━━━━━━━━━━━━━━\n"
            summary += f"✅ *Berhasil: {successful_files} file*\n"
            summary += f"👤 *Nama: {contact_name}*\n📞 *Total: {total_processed} kontak*\n"
            summary += f"🎨 *Custom pattern berhasil diterapkan*\n"
            summary += f"━━━━━━━━━━━━━━━━━━━\n💡 Gunakan /start untuk konversi baru."
            
            await update.message.reply_text(summary, parse_mode='Markdown')
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Error processing custom mode: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan saat memproses file custom.")
            context.user_data.clear()
    
    else:
        await update.message.reply_text("❌ Tidak ada operasi yang menunggu input. Gunakan /start untuk memulai.")

def main():
    """Start the bot"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("string", string_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    
    # Start bot
    print("🤖 VCF Generator Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
 