class PdfGenerationJob < ApplicationJob
  queue_as :default

  def perform(pdf_result_id)
    pdf_result = PdfResult.find(pdf_result_id)
    filename = "output_#{SecureRandom.hex(8)}.pdf"
    pdf_result.update(filename: filename, generation_state: "generating")

    Rails.logger.debug "[PdfGenerationJob] Starting PDF generation for PdfResult ID: #{pdf_result.id}"

    begin
      pdf_generation_url = ENV.fetch("PDF_GENERATION_URL")
      Rails.logger.debug "[PdfGenerationJob] PDF_GENERATION_URL: #{pdf_generation_url}"

      Puppeteer.launch(headless: true, args: [ "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--no-zygote" ]) do |browser|
        Rails.logger.debug "[PdfGenerationJob] Puppeteer launched. Creating new page."
        page = browser.new_page
        Rails.logger.debug "[PdfGenerationJob] Navigating to URL: #{pdf_generation_url}"
        page.goto(pdf_generation_url)
        Rails.logger.debug "[PdfGenerationJob] URL navigated. Generating PDF."
        page.pdf(path: "tmp/#{filename}", print_background: true, prefer_css_page_size: true, margin: { top: "0.5in", right: "0.5in", bottom: "0.5in", left: "0.5in" })
        Rails.logger.debug "[PdfGenerationJob] PDF generated. Closing page."
        page.close
        Rails.logger.debug "[PdfGenerationJob] Page closed."
      end

      pdf_result.update(generation_state: "completed")
      Rails.logger.debug "[PdfGenerationJob] PdfResult ID #{pdf_result.id} updated to completed."
      Turbo::StreamsChannel.broadcast_replace_to("pdf_results", target: "pdf_result_#{pdf_result.id}", partial: "home/pdf_result", locals: { pdf_result: pdf_result })

    rescue StandardError => e
      Rails.logger.error "[PdfGenerationJob] Error generating PDF for PdfResult ID #{pdf_result.id}: #{e.message}"
      Rails.logger.error e.backtrace.join("\n") if e.backtrace
      pdf_result.update(generation_state: "failed", error_message: e.message)
      Turbo::StreamsChannel.broadcast_replace_to("pdf_results", target: "pdf_result_#{pdf_result.id}", partial: "home/pdf_result", locals: { pdf_result: pdf_result })
    end
  end
end
