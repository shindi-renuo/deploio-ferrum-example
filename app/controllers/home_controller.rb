class HomeController < ApplicationController
  def index
  end

  def generate_pdf
    pdf_result = PdfResult.create(generation_state: "pending")
    PdfGenerationJob.perform_later(pdf_result.id)
    @pdf_result = pdf_result
  end

  def download_pdf
    Rails.logger.debug "Attempting to download PDF. Filename from params: #{params[:filename]}"
    pdf_result = PdfResult.find_by(filename: params[:filename])

    if pdf_result
      Rails.logger.debug "PdfResult found: ID=#{pdf_result.id}, GenerationState=#{pdf_result.generation_state}, Filename=#{pdf_result.filename}"
    else
      Rails.logger.debug "PdfResult not found for filename: #{params[:filename]}"
    end

    if pdf_result && pdf_result.generation_state == "completed" && File.exist?(Rails.root.join("tmp", pdf_result.filename))
      Rails.logger.debug "File exists and generation_state is completed. Sending file: tmp/#{pdf_result.filename}"
      send_file Rails.root.join("tmp", pdf_result.filename), filename: pdf_result.filename, type: "application/pdf", disposition: "attachment"
    elsif pdf_result && pdf_result.generation_state == "failed"
      Rails.logger.debug "PdfResult generation_state is failed. Error: #{pdf_result.error_message}"
      render plain: "PDF generation failed: #{pdf_result.error_message}", status: :internal_server_error
    else
      Rails.logger.debug "Conditions not met. PdfResult present: #{!pdf_result.nil?}, GenerationState completed: #{pdf_result&.generation_state == "completed"}, File exists: #{File.exist?("tmp/#{pdf_result&.filename}")}"
      render plain: "File not found or not yet generated. Please try again later.", status: :not_found
    end
  end
end
