class HomeController < ApplicationController
  def index
  end

  def generate_pdf
    browser = Ferrum::Browser.new(browser_path: ENV.fetch("BROWSER_PATH"), headless: true, timeout: 20, process_timeout: 20)
    link = "https://#{Rails.application.routes.default_url_options[:host]}/example"
    browser.go_to(link)
    browser.pdf(path: "example.pdf", paper_width: 1.0, paper_height: 1.0)
    browser.quit()
    send_file "example.pdf", filename: "example.pdf", type: "application/pdf"
  end
end
