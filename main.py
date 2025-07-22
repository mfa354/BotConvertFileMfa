import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import io
import re
import asyncio
import time

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "7758251892:AAEePbQRRFkN_1Us--S-VlIJ5eTSd_zr2ik"

# Menu configurations
MENUS = {
    'main': {
        'text': "🤖 *Selamat datang di VCF Generator Bot!*\n\nPilih menu di bawah ini:",
        'buttons': [
            [InlineKeyboardButton("📝 TEXT TO VCF", callback_data='text_to_vcf'), InlineKeyboardButton("📁 CV TXT TO VCF", callback_data='cv_txt_to_vcf')]
        ]
    },
    'cv_submenu': {
        'text': "📁 *CV TXT TO VCF - Pilih Mode:*\n\n🔧 *V1* - Upload TXT, pilih output mode (Default/Custom)",
        'buttons': [
            [InlineKeyboardButton("🔧 V1", callback_data='cv_v1'), InlineKeyboardButton("⬅️ Back", callback_data='back_to_main')]
        ]
    },
    'output_mode_selection': {
        'text': "🎉 *Upload Complete!*\n\n📋 *Pilih mode output:*\n\n🔹 **Default** - Nama file VCF sama dengan file TXT\n🔹 **Custom** - Nama file VCF sesuai input Anda\n\n*Pilih mode yang Anda inginkan:*",
        'buttons': [
            [InlineKeyboardButton("🔹 Default", callback_data='output_default'), InlineKeyboardButton("🎨 Custom", callback_data='output_custom')]
        ]
    },
    'text_instruction': "📝 *Format input:*\n```\nnama_file_vcf\n\nnama kontak\nnomer telepon\n\nnama kontak\nnomer telepon\n```",
    'cv_instruction': "📁 *Upload file TXT Anda*\n\n• Upload satu atau beberapa file sekaligus\n• Bot akan otomatis mendeteksi ketika upload selesai"
}

def clean_name_for_vcf(name):
    """Clean name to be VCF compatible while preserving emojis"""
    # Remove only problematic characters but keep emojis and Unicode
    # VCF format supports UTF-8, so emojis should work
    cleaned = re.sub(r'[;\n\r]', ' ', name)  # Remove VCF delimiters
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()  # Normalize spaces
    return cleaned

async def show_menu(message_target, menu_key, edit=False):
    """Show menu with configuration"""
    menu = MENUS[menu_key]
    reply_markup = InlineKeyboardMarkup(menu['buttons']) if 'buttons' in menu else None
    
    if edit:
        await message_target.edit_message_text(menu['text'], reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await message_target.reply_text(menu['text'], reply_markup=reply_markup, parse_mode='Markdown')

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
        'cv_v1': lambda: setup_cv_v1_mode(query, context),
        'output_default': lambda: setup_default_output(query, context),
        'output_custom': lambda: setup_custom_output(query, context),
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

def extract_phone_numbers(text: str) -> list:
    """Extract and clean phone numbers"""
    patterns = [r'\+?62\d{8,15}', r'0\d{8,15}', r'\+\d{10,15}', r'\d{10,15}']
    phones = []
    
    for pattern in patterns:
        for match in re.findall(pattern, text):
            clean = re.sub(r'[^\d+]', '', match)
            if 10 <= len(clean) <= 15 and len(set(clean.replace('+', ''))) >= 3:
                phones.append(clean)
    
    return list(dict.fromkeys(phones))  # Remove duplicates

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
    # Extract base name and starting number
    match = re.search(r'(.+?)(\d+)$', base_name)
    if not match:
        return []
    
    base_part = match.group(1)
    start_number = int(match.group(2))
    
    filenames = []
    for i in range(total_files):
        filename = f"{base_part}{start_number + i}.vcf"
        filenames.append(filename)
    
    return filenames

async def send_vcf_file(update, filename, vcf_content, stats_msg=None):
    """Send VCF file with optional caption"""
    vcf_file = io.BytesIO(vcf_content.encode('utf-8'))
    vcf_file.name = filename
    await update.message.reply_document(
        document=vcf_file, filename=filename,
        caption=stats_msg, parse_mode='Markdown' if stats_msg else None
    )

async def update_upload_status(update, context, file_count):
    """Update upload status message"""
    total_phones = sum(len(f['phone_numbers']) for f in context.user_data.get('txt_files_data', []))
    message_text = f"📤 *Menganalisis file...*\n\n✅ **{file_count} file** berhasil diproses\n📊 **{total_phones} nomor** ditemukan\n\n💡 *Menunggu file selanjutnya atau otomatis lanjut...*"
    
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
    
    # Update the menu text with file details
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

async def check_upload_completion(context):
    """Check if upload is complete and show output mode selection"""
    if (time.time() - context.user_data.get('last_upload_time', 0) >= 3.0 and 
        context.user_data.get('txt_files_data') and 
        context.user_data.get('waiting_for_txt_files')):
        
        await show_output_mode_selection(context)
        context.user_data['waiting_for_txt_files'] = False

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle TXT file uploads"""
    if not (context.user_data.get('waiting_for_txt_files') and context.user_data.get('cv_mode') == 'v1'):
        await update.message.reply_text("❌ Silakan gunakan menu untuk memulai proses konversi.")
        return
    
    document = update.message.document
    if not document.file_name.lower().endswith('.txt'):
        await update.message.reply_text("❌ Hanya file TXT yang diperbolehkan!")
        return
    
    try:
        file = await context.bot.get_file(document.file_id)
        file_content = await file.download_as_bytearray()
        
        # Try multiple encodings
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
        
        await update_upload_status(update, context, len(context.user_data['txt_files_data']))
        asyncio.create_task(delayed_check(context))
        
    except Exception as e:
        logger.error(f"Error processing TXT file: {e}")
        await update.message.reply_text("❌ Terjadi kesalahan saat memproses file TXT.")

async def delayed_check(context):
    """Delayed upload completion check"""
    await asyncio.sleep(4.0)
    await check_upload_completion(context)

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for all modes"""
    user_input = update.message.text.strip()
    
    # TEXT TO VCF mode
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
            stats_msg += f"━━━━━━━━━━━━━━━━━━━\n🔢 *Total: {total_contacts} kontak*"
            
            await send_vcf_file(update, filename, vcf_content, stats_msg)
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Error processing VCF: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan saat memproses input.")
            context.user_data.clear()
    
    # Custom filename input
    elif context.user_data.get('waiting_for_custom_filename'):
        # Validate custom filename format
        if not re.search(r'\d+$', user_input):
            await update.message.reply_text("❌ Nama file harus diakhiri dengan angka!\n\n💡 **Contoh:** pudidi1, amanai-5, contact123")
            return
        
        context.user_data['custom_base_name'] = user_input
        context.user_data['waiting_for_custom_filename'] = False
        context.user_data['waiting_for_contact_name'] = True
        
        txt_files_data = context.user_data.get('txt_files_data', [])
        total_files = len(txt_files_data)
        
        # Preview filenames
        preview_filenames = generate_custom_filenames(user_input, min(5, total_files))
        preview_text = f"✅ *Nama file diterima!*\n\n📋 *Preview nama file:*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        for filename in preview_filenames:
            preview_text += f"📄 **{filename}**\n"
        if total_files > 5:
            last_filename = generate_custom_filenames(user_input, total_files)[-1]
            preview_text += f"📄 ... hingga **{last_filename}**\n"
        
        preview_text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📁 **Total**: {total_files} file\n\n👤 **Ketik nama kontak untuk semua file VCF:**"
        
        await update.message.reply_text(preview_text, parse_mode='Markdown')
    
    # Contact name input (both default and custom modes)
    elif context.user_data.get('waiting_for_contact_name') and context.user_data.get('cv_mode') == 'v1':
        if not user_input:
            await update.message.reply_text("❌ Nama kontak tidak boleh kosong!")
            return
        
        try:
            txt_files_data = context.user_data.get('txt_files_data', [])
            if not txt_files_data:
                await update.message.reply_text("❌ Data file tidak ditemukan. Silakan mulai ulang dengan /start")
                context.user_data.clear()
                return
            
            processing_msg = await update.message.reply_text("🔄 Sedang memproses dan mengirim file VCF...")
            
            successful_files = 0
            total_contacts = 0
            output_mode = context.user_data.get('output_mode', 'default')
            
            # Generate filenames based on mode
            if output_mode == 'custom':
                custom_base = context.user_data.get('custom_base_name', '')
                filenames = generate_custom_filenames(custom_base, len(txt_files_data))
            else:  # default mode
                filenames = [file_data['filename'].rsplit('.txt', 1)[0] + '.vcf' for file_data in txt_files_data]
            
            for i, file_data in enumerate(txt_files_data):
                try:
                    filename = filenames[i] if i < len(filenames) else f"contact_{i+1}.vcf"
                    vcf_content = create_vcf_from_phones(file_data['phone_numbers'], user_input)
                    
                    if vcf_content:
                        await send_vcf_file(update, filename, vcf_content)
                        successful_files += 1
                        total_contacts += len(file_data['phone_numbers'])
                        await asyncio.sleep(0.3)  # Rate limiting
                        
                except Exception as e:
                    logger.error(f"Error processing file: {e}")
            
            try:
                await processing_msg.delete()
            except:
                pass
            
            mode_text = "🔹 Default" if output_mode == 'default' else "🎨 Custom"
            summary = f"🎉 *KONVERSI SELESAI!*\n\n📊 *RINGKASAN:*\n━━━━━━━━━━━━━━━━━━━\n"
            summary += f"✅ *Berhasil: {successful_files}/{len(txt_files_data)} file*\n"
            summary += f"🎯 *Mode: {mode_text}*\n"
            summary += f"👤 *Nama kontak: {user_input}*\n📞 *Total kontak: {total_contacts} kontak*\n"
            summary += f"━━━━━━━━━━━━━━━━━━━\n💡 Gunakan /start untuk konversi baru."
            
            await update.message.reply_text(summary, parse_mode='Markdown')
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Error creating VCF: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan saat membuat file VCF.")
            context.user_data.clear()
    
    else:
        await update.message.reply_text("Gunakan /start untuk melihat menu atau pilih salah satu fitur yang tersedia.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("string", string_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    application.add_error_handler(error_handler)
    
    print("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
