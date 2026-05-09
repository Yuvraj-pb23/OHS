import sys

with open("/home/hanuai/Documents/Websites/OHS/OHS/templates/posh_act_page_corp.html", "r") as f:
    content = f.read()

target = """    <div class="top-header">
      <h3 style="color: var(--primary); margin: 0; font-weight: 700;">POSH Training Mastery</h3>
      <div class="user-profile-wrapper">
        <div class="user-profile-top" id="userProfileBtn">
          <span class="user-name-top">{{ request.user.get_full_name|default:request.user.username|title }}</span>
          <div class="user-avatar-top">
            {{ request.user.username|slice:":1"|upper }}
          </div>
        </div>
        <div class="user-dropdown-menu" id="userDropdown">
          <a href="javascript:void(0);" onclick="showLogoutModal()">
            <i class="fa-solid fa-arrow-right-from-bracket"></i> Logout
          </a>
        </div>
      </div>
    </div>"""

replacement = """    <!-- PREMIUM LOGOUT CONFIRMATION MODAL -->
    <div class="custom-modal-overlay" id="logoutConfirmModal">
      <div class="logout-modal-content">
        <div class="logout-icon-wrapper">
          <i class="fa-solid fa-arrow-right-from-bracket"></i>
        </div>
        <h3 class="logout-modal-title">Are you sure to exit?</h3>
        <p class="logout-modal-text">You are about to end your session. Make sure you have saved all your progress before logging out.</p>
        <div style="display: flex; flex-direction: column; gap: 10px;">
          <a href="{% url 'training_logout' %}" class="btn-logout-confirm">Yes, Logout Now</a>
          <button type="button" class="btn-logout-cancel" onclick="closeLogoutModal()">Stay on Dashboard</button>
        </div>
      </div>
    </div>

    <div class="top-header">
      <h3 style="color: var(--primary); margin: 0; font-weight: 700;">POSH Training Mastery</h3>
      <div class="user-profile-wrapper">
        <div class="user-profile-top" id="userProfileBtn">
          <span class="user-name-top">{{ request.user.get_full_name|default:request.user.username|title }}</span>
          <div class="user-avatar-top">
            {{ request.user.username|slice:":1"|upper }}
          </div>
        </div>
        <div class="user-dropdown-menu" id="userDropdown">
          <a href="javascript:void(0);" onclick="showLogoutModal()">
            <i class="fa-solid fa-arrow-right-from-bracket"></i> Logout
          </a>
        </div>
      </div>
    </div>"""

if target in content:
    new_content = content.replace(target, replacement)
    with open("/home/hanuai/Documents/Websites/OHS/OHS/templates/posh_act_page_corp.html", "w") as f:
        f.write(new_content)
    print("Success")
else:
    print("Target not found")
