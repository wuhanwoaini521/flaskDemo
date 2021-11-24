import click
from flask import Flask, escape, render_template, request, url_for, redirect, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os
import sys

WIN = sys.platform.startswith("win")
if WIN:
    prefix = "sqlite:///"
else:
    prefix = "sqlite:////"

app = Flask(__name__)
login_manager =  LoginManager(app) # 实例化扩展类（登录扩展）
login_manager.login_view = 'login'

app.config['SQLALCHEMY_DATABASE_URI'] = prefix + os.path.join(app.root_path, 'data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # 关闭对模型修改的监控
app.config['SECRET_KEY'] = 'dev' # 设置session对象
db = SQLAlchemy(app) # 初始化扩展，传入程序实例app

# 创建数据库模型
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True) # 主键
    name = db.Column(db.String(20)) # 用户名字
    username = db.Column(db.String(20)) # 用户名
    password_hash = db.Column(db.String(128)) # 密码散列值

    def set_password(self, password): # 用来设置密码得方法，接受密码作为参数
        self.password_hash = generate_password_hash(password) # 将生成得密码保持到对应字段

    def validate_password(self, password): # 用来验证密码得方法，接受密码作为参数
        return check_password_hash(self.password_hash, password) # 返回布尔值

class Movie(db.Model):
    id = db.Column(db.Integer, primary_key=True) # 主键
    title = db.Column(db.String(60)) # 电影标题
    year = db.Column(db.String(4)) # 电影年份

# 注册自定义命令
@app.cli.command()
@click.option('--drop', is_flag = True, help='Create after drop.')
def initdb(drop):
    if drop:
        db.drop_all()
    db.create_all()
    click.echo("Initialized database.")

# 创建一个 初始化数据得函数
@app.cli.command()
def forge():
    db.create_all()

    name = 'Wu Han'
    movies = [
        {'title': 'My Neighbor Totoro', 'year': '1988'},
        {'title': 'Dead Poets Society', 'year': '1989'},
        {'title': 'A Perfect World', 'year': '1993'},
        {'title': 'Leon', 'year': '1994'},
        {'title': 'Mahjong', 'year': '1996'},
        {'title': 'Swallowtail Butterfly', 'year': '1996'},
        {'title': 'King of Comedy', 'year': '1999'},
        {'title': 'Devils on the Doorstep', 'year': '1999'},
        {'title': 'WALL-E', 'year': '2008'},
        {'title': 'The Pork of Music', 'year': '2012'},
    ]

    user = User(name=name)
    db.session.add(user)
    for m in movies:
        movie = Movie(title=m['title'], year=m['year'])
        db.session.add(movie)

    db.session.commit()
    click.echo('Done!')

# 添加模板上下文函数 （作用是，后面如果有方法想要用到 user 这个变量， 但是后边 得方法就不需要添加了，这个方法给他全部添加了进去（相当于添加成了全局变量））
@app.context_processor
def inject_user():
    user = User.query.first()
    return dict(user = user)

# 报错页面
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# 主界面方法
@app.route('/', methods=["GET","POST"])
def index():
    if request.method == "POST":
        if not current_user.is_authenticated:
            return redirect(url_for('index'))
        title = request.form.get("title")
        year = request.form.get("year")
        if not title or not year or len(year) !=4 or len(title) > 60:
            flash("Invalid input.")
            return redirect(url_for("index"))

        movie = Movie(title= title, year = year)
        db.session.add(movie)
        db.session.commit()
        flash("Item created.")
        return redirect(url_for("index"))

    movies = Movie.query.all()
    return render_template("index.html", movies = movies)

# 编辑电影条目
@app.route("/movie/edit/<int:movie_id>", methods=["GET","POST"])
@login_required
def edit(movie_id):
    movie = Movie.query.get_or_404(movie_id)

    if request.method == "POST":
        title = request.form['title']
        year = request.form['year']

        if not title or not year or len(year) != 4 or len(title)> 60:
            flash('Invalid input.')
            return redirect(url_for('edit'), movie_id = movie_id) # 重定向会对应得编辑页面
        movie.title = title
        movie.year = year
        db.session.commit()
        flash("Item updated.")
        return redirect(url_for('index'))
    return render_template('edit.html', movie = movie)

# 删除条目
@app.route("/movie/delete/<int:movie_id>", methods=["POST"])
@login_required
def delete(movie_id):
    movie = Movie.query.get_or_404(movie_id)
    db.session.delete(movie)
    db.session.commit()
    flash("Item deleted.")
    return redirect(url_for("index")) # 重定向回主页

# 生成管理员账户
@app.cli.command()
@click.option('--username', prompt = True, help='The username used to login.')
@click.option('--password', prompt = True, hide_input = True, confirmation_prompt = True, help='The password used to login.')
def admin(username, password):
    db.create_all()

    user = User.query.first()
    if user is None:
        click.echo("Updating user...")
        user.username = username
        user.set_password(password)
    else:
        click.echo("Creating user...")
        user = User(username = username, name="Admin")
        user.set_password(password)
        db.session.add(user)
    db.session.commit()
    click.echo("Done.")

# 初始化Flask-login
@login_manager.user_loader
def load_user(user_id): # 创建用户加载回调函数，接受用户Id作为参数
    user = User.query.get(int(user_id)) # 用id作为User 模型得主键查询对应得用户
    return user # 返回用户对象


# 用户登录
@app.route("/login", methods=['GET','POST'])
def login():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']

        if not username or not password:
            flash("Invalid input.")
            return redirect(url_for('login'))

        user = User.query.first()
        # 验证用户名和密码是否一致
        if username == user.username and user.validate_password(password):

            login_user(user) #登入用户
            flash("Login success.")
            return redirect(url_for('index'))
        flash('Invalid username or password.')
        return redirect(url_for('login'))
    return render_template('login.html')

# 登出
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Bye.")
    return redirect(url_for('index'))

from flask_login import login_required, current_user

# ...

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        name = request.form['name']

        if not name or len(name) > 20:
            flash('Invalid input.')
            return redirect(url_for('settings'))

        current_user.name = name
        # current_user 会返回当前登录用户的数据库记录对象
        # 等同于下面的用法
        # user = User.query.first()
        # user.name = name
        db.session.commit()
        flash('Settings updated.')
        return redirect(url_for('index'))

    return render_template('settings.html')

if __name__ == '__main__':
    app.run()
