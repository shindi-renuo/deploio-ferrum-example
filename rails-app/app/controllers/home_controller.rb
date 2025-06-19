class HomeController < ApplicationController
  def index
    @url = params[:url] || "https://www.google.com"
  end

  def generate_pdf
    url = params[:url]

    if url.blank?
      flash[:alert] = "Please provide a valid URL"
      redirect_to root_path
      return
    end

    # Validate URL format
    begin
      uri = URI.parse(url)
      unless uri.is_a?(URI::HTTP) || uri.is_a?(URI::HTTPS)
        flash[:alert] = "Please provide a valid HTTP or HTTPS URL"
        redirect_to root_path
        return
      end
    rescue URI::InvalidURIError
      flash[:alert] = "Please provide a valid URL"
      redirect_to root_path
      return
    end

    begin
      response = HTTParty.post(
        "#{ENV.fetch('PYTHON_SERVICE_URL', 'http://localhost:5000')}/generate_pdf",
        body: { url: url }.to_json,
        headers: {
          "Content-Type" => "application/json",
          "Accept" => "application/json"
        },
        timeout: 10
      )

      if response.code == 202
        parsed = response.parsed_response
        task_id = parsed["task_id"]

        if task_id
          redirect_to home_pdf_status_path(task_id: task_id)
        else
          flash[:alert] = "Failed to get task ID from PDF service"
          redirect_to root_path
        end
      elsif response.code == 503
        flash[:alert] = "PDF service is busy. Please try again in a few moments."
        redirect_to root_path
      else
        parsed = response.parsed_response
        error_message = parsed&.dig("detail") || "Failed to initiate PDF generation"
        flash[:alert] = error_message
        redirect_to root_path
      end

    rescue HTTParty::Error, Net::TimeoutError, Errno::ECONNREFUSED => e
      Rails.logger.error "PDF service error: #{e.message}"
      flash[:alert] = "PDF service is currently unavailable. Please try again later."
      redirect_to root_path
    rescue StandardError => e
      Rails.logger.error "Unexpected error in generate_pdf: #{e.message}"
      flash[:alert] = "An unexpected error occurred. Please try again."
      redirect_to root_path
    end
  end

  def pdf_status
    @task_id = params[:task_id]
    if @task_id.blank?
      if request.xhr? || request.format.json?
        render json: { error: "Invalid PDF task ID." }, status: 400
        return
      else
        redirect_to root_path, alert: "Invalid PDF task ID."
        return
      end
    end

    begin
      response = HTTParty.get(
        "#{ENV.fetch('PYTHON_SERVICE_URL', 'http://localhost:5000')}/pdf_status/#{@task_id}",
        headers: { "Accept" => "application/json" },
        timeout: 10
      )

      if response.code == 404
        error_msg = "PDF task not found or expired."
        if request.xhr? || request.format.json?
          render json: { error: error_msg }, status: 404
          return
        else
          flash[:alert] = error_msg
          redirect_to root_path
          return
        end
      elsif response.code != 200
        error_msg = "Error checking PDF status. Please try again."
        if request.xhr? || request.format.json?
          render json: { error: error_msg }, status: response.code
          return
        else
          flash[:alert] = error_msg
          redirect_to root_path
          return
        end
      end

      @status = response.parsed_response
      @processing_time = @status["processing_time"]

      # Handle JSON requests
      if request.xhr? || request.format.json?
        render json: {
          task_id: @task_id,
          status: @status["status"],
          processing_time: @processing_time,
          pdf_url: @status["pdf_url"],
          pdf_file_name: @status["pdf_file_name"],
          error: @status["error"],
          created_at: @status["created_at"],
          completed_at: @status["completed_at"]
        }
        return
      end

      # Handle completed PDFs by triggering download (for regular requests)
      if @status["status"] == "completed" && @status["pdf_url"]
        download_pdf_file(@status["pdf_url"], @status["pdf_file_name"])
      elsif @status["status"] == "failed"
        flash[:alert] = "PDF generation failed: #{@status['error'] || 'Unknown error'}"
        redirect_to root_path
      end
      # For pending/processing/queued, just render the status page

    rescue HTTParty::Error, Net::TimeoutError, Errno::ECONNREFUSED => e
      Rails.logger.error "PDF status check error: #{e.message}"
      error_msg = "Unable to check PDF status. Service may be unavailable."
      if request.xhr? || request.format.json?
        render json: { error: error_msg }, status: 503
      else
        flash[:alert] = error_msg
        redirect_to root_path
      end
    rescue StandardError => e
      Rails.logger.error "Unexpected error in pdf_status: #{e.message}"
      error_msg = "An unexpected error occurred while checking status."
      if request.xhr? || request.format.json?
        render json: { error: error_msg }, status: 500
      else
        flash[:alert] = error_msg
        redirect_to root_path
      end
    end
  end

  def download_pdf
    task_id = params[:task_id]

    if task_id.blank?
      redirect_to root_path, alert: "Invalid task ID"
      return
    end

    begin
      # Get the current status to get the PDF URL
      response = HTTParty.get(
        "#{ENV.fetch('PYTHON_SERVICE_URL', 'http://localhost:5000')}/pdf_status/#{task_id}",
        headers: { "Accept" => "application/json" },
        timeout: 10
      )

             if response.code == 200
         status = response.parsed_response
         if status["status"] == "completed" && status["pdf_url"]
           download_pdf_file(status["pdf_url"], status["pdf_file_name"])
         else
           flash[:alert] = "PDF is not ready for download"
           redirect_to home_pdf_status_path(task_id: task_id)
         end
      else
        flash[:alert] = "Unable to retrieve PDF information"
        redirect_to root_path
      end

    rescue StandardError => e
      Rails.logger.error "Error downloading PDF: #{e.message}"
      flash[:alert] = "Error downloading PDF"
      redirect_to root_path
    end
  end

  private

  def download_pdf_file(pdf_url, filename)
    begin
      pdf_response = HTTParty.get(pdf_url, timeout: 30)

      if pdf_response.success?
        send_data pdf_response.body,
                  filename: filename || "document.pdf",
                  type: "application/pdf",
                  disposition: "attachment"
      else
        flash[:alert] = "Failed to download PDF file"
        redirect_to root_path
      end
    rescue StandardError => e
      Rails.logger.error "PDF download error: #{e.message}"
      flash[:alert] = "Error downloading PDF file"
      redirect_to root_path
    end
  end
end
